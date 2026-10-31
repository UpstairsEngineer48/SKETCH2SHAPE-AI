from pathlib import Path
from time import perf_counter
from uuid import uuid4

import numpy as np
import onnxruntime as ort
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from .config import MAX_UPLOAD_MB, MODEL_FILES, MODEL_DIR, OUTPUT_DIR, model_path
from .image_preprocess import preprocess_image
from .ort_utils import create_session_options, get_dinov2_session

app = FastAPI(
    title="Sketch2Shape AI — Image Conditioning API",
    version="0.2.0",
    description=(
        "CPU-only preprocessing and DINOv2 ONNX conditioning API. "
        "This connected stage does not yet run DiT sampling, ShapeVAE, "
        "mesh extraction, or GLB export."
    ),
)

# The Vite development proxy is used by default. These origins also allow a
# separately served local frontend to call FastAPI directly during development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/outputs", StaticFiles(directory=str(OUTPUT_DIR)), name="outputs")


@app.get("/")
def root():
    return {
        "name": "Sketch2Shape AI",
        "status": "online",
        "docs": "/docs",
        "frontend": "Run the Vite frontend separately on http://localhost:5173",
    }


@app.get("/health")
def health():
    dino_ready = model_path("dinov2").is_file()
    return {
        "status": "ok",
        "runtime": "onnxruntime",
        "available_providers": ort.get_available_providers(),
        "selected_provider": "CPUExecutionProvider",
        "model_directory": str(MODEL_DIR),
        "conditioner_model_available": dino_ready,
        "conditioner_model_loaded": get_dinov2_session.cache_info().currsize > 0,
        "graphs": {
            key: {"file": filename, "exists": model_path(key).is_file()}
            for key, filename in MODEL_FILES.items()
        },
        "generation_stage": "preprocessing + DINOv2 conditioning only",
        "mesh_generation_available": False,
    }


@app.get("/models/info")
def models_info():
    """Load each graph one at a time and report its ONNX signature."""
    result = {}
    for key, filename in MODEL_FILES.items():
        path = model_path(key)
        if not path.is_file():
            result[key] = {"file": filename, "status": "missing"}
            continue
        try:
            session = ort.InferenceSession(
                str(path),
                sess_options=create_session_options(),
                providers=["CPUExecutionProvider"],
            )
            result[key] = {
                "file": filename,
                "status": "loaded",
                "providers": session.get_providers(),
                "inputs": [
                    {"name": item.name, "shape": item.shape, "type": item.type}
                    for item in session.get_inputs()
                ],
                "outputs": [
                    {"name": item.name, "shape": item.shape, "type": item.type}
                    for item in session.get_outputs()
                ],
            }
            del session
        except Exception as exc:  # return graph-specific diagnostics to the user
            result[key] = {"file": filename, "status": "load_error", "error": str(exc)}
    return result


@app.post("/debug/conditioner")
async def run_conditioner(
    image: UploadFile = File(...),
    input_type: str = Form("auto"),
    remove_background: bool = Form(True),
    prompt: str = Form(""),
):
    """Run preprocessing + DINOv2 conditioning and return inspectable artifacts.

    `prompt` is accepted so the current frontend form is fully connected, but
    DINOv2 is an image conditioner and this stage does not consume text prompts.
    """
    content = await image.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded image is empty.")
    if len(content) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail=f"Image exceeds the {MAX_UPLOAD_MB} MB upload limit.",
        )

    try:
        prep = await run_in_threadpool(
            preprocess_image, content, input_type, remove_background
        )
        pixels = np.asarray(prep.model_image, dtype=np.float32) / 255.0
        tensor = np.transpose(pixels, (2, 0, 1))[None, ...].astype(np.float32)

        # Unique output folder per request prevents the browser from showing
        # stale previews when the user processes several sketches in a row.
        request_id = uuid4().hex
        artifact_dir = OUTPUT_DIR / "preprocessing" / request_id
        artifact_dir.mkdir(parents=True, exist_ok=True)
        prep.model_image.save(artifact_dir / "model_input.png")
        prep.foreground_rgba.save(artifact_dir / "foreground.png")
        prep.mask.save(artifact_dir / "mask.png")
        prep.edge_map.save(artifact_dir / "canny_edges.png")

        session = await run_in_threadpool(get_dinov2_session)
        input_name = session.get_inputs()[0].name
        output_name = session.get_outputs()[0].name
        start = perf_counter()
        outputs = await run_in_threadpool(
            session.run, [output_name], {input_name: tensor}
        )
        elapsed = perf_counter() - start
        conditioner_output = outputs[0]

        artifact_base = f"/outputs/preprocessing/{request_id}"
        artifact_urls = {
            "model_input": f"{artifact_base}/model_input.png",
            "foreground": f"{artifact_base}/foreground.png",
            "mask": f"{artifact_base}/mask.png",
            "canny_edges": f"{artifact_base}/canny_edges.png",
        }
        return {
            "status": "conditioner_ok",
            "request_id": request_id,
            "stage_completed": "DINOv2 image conditioning",
            "preprocessing": {
                "method": prep.method,
                "requested_input_type": input_type,
                "background_removed": prep.method in {
                    "rembg_cpu", "adaptive_sketch_threshold", "existing_alpha"
                },
                "model_input": "RGB, centered on white, 1022x1022, float32 [0,1]",
                "edge_detection": "Canny 50/150 generated for diagnostics only; not fed to DINOv2",
            },
            "artifact_urls": artifact_urls,
            "embedding_shape": list(conditioner_output.shape),
            "embedding_dtype": str(conditioner_output.dtype),
            "inference_seconds": round(elapsed, 3),
            "prompt_received": bool(prompt.strip()),
            "prompt_used": False,
            "prompt_note": (
                "Text guidance is received from the UI but is not used by the current DINOv2-only stage."
                if prompt.strip() else None
            ),
            "next_stage": "DiT Turbo sampling + ShapeVAE + mesh extraction (not implemented yet)",
            "mesh_generation_available": False,
        }
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Preprocessing/DINOv2 ONNX inference failed: {type(exc).__name__}: {exc}",
        ) from exc
