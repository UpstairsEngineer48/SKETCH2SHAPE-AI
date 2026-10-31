import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_DIR = Path(os.getenv("SKETCH2SHAPE_OUTPUT_DIR", str(ROOT_DIR / "outputs"))).resolve()
MODEL_DIR = Path(os.getenv(
    "HUNYUAN_ONNX_MODEL_DIR",
    str(ROOT_DIR / "models" / "hunyuan3d-2mini-turbo-onnx"),
)).resolve()
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "20"))
ORT_INTRA_OP_THREADS = int(os.getenv("ORT_INTRA_OP_THREADS", "4"))

MODEL_FILES = {
    "dinov2": "dinov2_giant_1022_int8.onnx",
    "dit": "dit_turbo.onnx",
    "vae_kv": "vae_kv.onnx",
    "vae_query": "vae_query.onnx",
}


def model_path(key: str) -> Path:
    return MODEL_DIR / MODEL_FILES[key]
