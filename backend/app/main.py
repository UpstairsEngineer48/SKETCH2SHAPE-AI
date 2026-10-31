"""FastAPI application for the Sketch2Shape image-to-3D pipeline."""

from __future__ import annotations

import logging
from io import BytesIO
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from PIL import Image, UnidentifiedImageError
from starlette.concurrency import run_in_threadpool

from .background_removal import remove_background_image
from .export import MeshValidationError
from .preprocessing import (
    is_white_paper_sketch,
    prepare_image,
    save_prepared_image,
    validate_image_bytes,
)
from .triposr import TripoSRNotInstalledError, TripoSRReconstructor

BACKEND_DIR = Path(__file__).resolve().parents[1]
try:
    from dotenv import load_dotenv

    load_dotenv(BACKEND_DIR / ".env")
except ImportError:
    # Environment variables can also be supplied directly by the shell.
    pass

OUTPUT_DIR = Path(os.getenv("SKETCH2SHAPE_OUTPUT_DIR", str(BACKEND_DIR / "outputs"))).resolve()
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_MB", "15")) * 1024 * 1024
RECONSTRUCTION_FORMAT = os.getenv("OUTPUT_FORMAT", "glb").lower()
MESH_RESOLUTION = int(os.getenv("MESH_RESOLUTION", "256"))
CONTROLNET_ENABLED = os.getenv("CONTROLNET_ENABLED", "0").lower() in {"1", "true", "yes"}
REMOVE_BACKGROUND_UPLOADS = os.getenv("REMOVE_BACKGROUND_UPLOADS", "1").lower() in {"1", "true", "yes"}

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("sketch2shape")
reconstructor = TripoSRReconstructor()


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Model initialization is lazy: the API can start and answer /health while
    # model weights are downloaded on the first /generate call.
    yield


app = FastAPI(
    title="Sketch2Shape AI API",
    version="0.2.0",
    description="Sketch/image preprocessing and pretrained single-image 3D reconstruction.",
    lifespan=lifespan,
)

allowed_origins = [
    value.strip()
    for value in os.getenv(
        "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",")
    if value.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
app.mount("/assets", StaticFiles(directory=str(OUTPUT_DIR)), name="assets")


@app.get("/")
def root():
    return {"name": "Sketch2Shape AI", "docs": "/docs", "health": "/health"}


@app.get("/health")
def health():
    return {
        "status": "ok",
        "model_loaded": reconstructor.is_loaded,
        "model": "TripoSR",
        "device": reconstructor.device,
        "controlnet_enabled": CONTROLNET_ENABLED,
    }


def _run_reconstruction(
    prepared_image: Image.Image,
    output_path: Path,
    file_format: str,
) -> tuple[Path, dict]:
    return reconstructor.generate(
        image=prepared_image,
        output_path=output_path,
        file_format=file_format,
        mesh_resolution=MESH_RESOLUTION,
    )


@app.post("/generate")
async def generate(
    image: UploadFile = File(...),
    input_type: str = Form("upload"),
    prompt: str = Form(""),
    file_format: str = Form(RECONSTRUCTION_FORMAT),
):
    if input_type not in {"draw", "upload"}:
        raise HTTPException(status_code=400, detail="input_type must be 'draw' or 'upload'.")
    file_format = file_format.lower().lstrip(".")
    if file_format not in {"glb", "obj"}:
        raise HTTPException(status_code=400, detail="file_format must be 'glb' or 'obj'.")
    if len(prompt) > 400:
        raise HTTPException(status_code=400, detail="Prompt must be 400 characters or fewer.")

    raw = await image.read()
    try:
        validate_image_bytes(raw, MAX_UPLOAD_BYTES)
        source = Image.open(BytesIO(raw))
        source.load()
        source = source.convert("RGBA" if "A" in source.getbands() else "RGB")
    except (ValueError, UnidentifiedImageError, OSError) as exc:
        raise HTTPException(status_code=400, detail=f"Invalid image upload: {exc}") from exc

    job_id = uuid.uuid4().hex[:12]
    job_dir = OUTPUT_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    source_path = job_dir / "source.png"
    prepared_path = job_dir / "prepared.png"
    source.save(source_path, format="PNG")

    try:
        base_image = source
        if (
            input_type == "upload"
            and not ("A" in source.getbands() and source.getchannel("A").getextrema()[0] < 250)
            and not is_white_paper_sketch(source)
            and REMOVE_BACKGROUND_UPLOADS
        ):
            base_image = await run_in_threadpool(remove_background_image, source)

        prepared_input = prepare_image(base_image, input_type=input_type)
        if CONTROLNET_ENABLED:
            from .controlnet import enhance_with_controlnet

            refined_image = await run_in_threadpool(
                enhance_with_controlnet,
                prepared_input,
                prompt,
            )
            prepared = prepare_image(refined_image, input_type="upload")
            prompt_used = bool(prompt.strip())
            note = (
                "The supplied prompt and sketch edges guided ControlNet image refinement before 3D reconstruction."
                if prompt.strip()
                else "Sketch edges and a default product-render description guided ControlNet image refinement."
            )
        else:
            prepared = prepared_input
            prompt_used = False
            note = (
                "This reconstruction used the image only. TripoSR does not consume text prompts; "
                "enable CONTROLNET_ENABLED=1 to add the optional prompt-guided refinement stage."
                if prompt.strip()
                else "Single-image TripoSR reconstruction."
            )

        save_prepared_image(prepared, prepared_path)
        output_path = job_dir / f"model.{file_format}"
        model_path, stats = await run_in_threadpool(
            _run_reconstruction,
            prepared,
            output_path,
            file_format,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except TripoSRNotInstalledError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except MeshValidationError as exc:
        logger.exception("Mesh validation failed for job %s", job_id)
        raise HTTPException(status_code=500, detail=f"3D mesh validation failed: {exc}") from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("3D reconstruction failed for job %s", job_id)
        raise HTTPException(
            status_code=500,
            detail=f"3D reconstruction failed: {exc}",
        ) from exc

    model_url = f"/assets/{job_id}/{model_path.name}"
    return {
        "job_id": job_id,
        "model_url": model_url,
        "format": file_format,
        "filename": f"sketch2shape-{job_id}.{file_format}",
        "prompt_used": prompt_used,
        "note": note,
        "mesh": stats,
    }
