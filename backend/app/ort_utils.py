from functools import lru_cache
import os

import onnxruntime as ort

from .config import model_path


def create_session_options() -> ort.SessionOptions:
    options = ort.SessionOptions()
    options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    options.intra_op_num_threads = max(1, int(os.getenv("ORT_INTRA_OP_THREADS", "4")))
    options.inter_op_num_threads = 1
    # Avoid retaining large memory-pattern buffers for variable workloads.
    options.enable_mem_pattern = False
    return options


@lru_cache(maxsize=1)
def get_dinov2_session() -> ort.InferenceSession:
    path = model_path("dinov2")
    if not path.is_file():
        raise FileNotFoundError(
            f"DINOv2 graph not found: {path}. Run `python download_models.py` first."
        )
    return ort.InferenceSession(
        str(path),
        sess_options=create_session_options(),
        providers=["CPUExecutionProvider"],
    )
