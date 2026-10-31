"""Lazy, process-local integration with the official VAST-AI TripoSR code."""

from __future__ import annotations

import gc
import os
import sys
import threading
from pathlib import Path

from PIL import Image

from .export import export_mesh


class TripoSRNotInstalledError(RuntimeError):
    pass


class TripoSRReconstructor:
    """Load TripoSR once and reuse it for requests.

    The upstream repository is kept outside this project at ``backend/vendor/TripoSR``
    (or at the path supplied in ``TRIPOSR_REPO``). Its own requirements should
    be installed into the same Python environment as this FastAPI service.
    """

    def __init__(self) -> None:
        self._model = None
        self._torch = None
        self._device = None
        self._lock = threading.Lock()

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    @property
    def device(self) -> str:
        if self._device:
            return str(self._device)
        return "cuda" if self._cuda_available() else "cpu"

    @staticmethod
    def _repo_path() -> Path:
        configured = os.getenv("TRIPOSR_REPO", "")
        if configured:
            return Path(configured).expanduser().resolve()
        return Path(__file__).resolve().parents[1] / "vendor" / "TripoSR"

    @staticmethod
    def _cuda_available() -> bool:
        try:
            import torch
            return bool(torch.cuda.is_available())
        except ImportError:
            return False

    def _load_model(self) -> None:
        if self._model is not None:
            return

        repo_path = self._repo_path()
        if not (repo_path / "tsr" / "system.py").is_file():
            raise TripoSRNotInstalledError(
                "TripoSR source was not found. Run the setup instructions in README.md "
                f"or set TRIPOSR_REPO to a TripoSR checkout. Expected: {repo_path}"
            )

        if str(repo_path) not in sys.path:
            sys.path.insert(0, str(repo_path))

        try:
            import torch
            from tsr.system import TSR
        except ImportError as exc:
            raise TripoSRNotInstalledError(
                "TripoSR dependencies are missing. Install the official TripoSR "
                "requirements in the backend Python environment."
            ) from exc

        device = "cuda:0" if torch.cuda.is_available() else "cpu"
        model_id = os.getenv("TRIPOSR_MODEL_ID", "stabilityai/TripoSR")
        chunk_size = int(os.getenv("TRIPOSR_CHUNK_SIZE", "4096"))

        try:
            model = TSR.from_pretrained(
                model_id,
                config_name="config.yaml",
                weight_name="model.ckpt",
            )
            model.renderer.set_chunk_size(chunk_size)
            model.to(device)
            model.eval()
        except Exception as exc:
            raise RuntimeError(
                "Could not load TripoSR. Check the Hugging Face model download, "
                "PyTorch/CUDA installation, and available memory."
            ) from exc

        self._torch = torch
        self._device = device
        self._model = model

    def generate(
        self,
        image: Image.Image,
        output_path: str | Path,
        file_format: str = "glb",
        mesh_resolution: int = 256,
    ) -> tuple[Path, dict]:
        """Infer a mesh from one prepared RGB image and export the validated asset."""
        with self._lock:
            self._load_model()
            torch = self._torch
            try:
                with torch.inference_mode():
                    scene_codes = self._model([image.convert("RGB")], device=self._device)
                    meshes = self._model.extract_mesh(
                        scene_codes,
                        True,  # return vertex colors; GLB can preserve them
                        resolution=mesh_resolution,
                    )
                if not meshes:
                    raise RuntimeError("TripoSR returned no mesh for this image.")
                destination = export_mesh(meshes[0], output_path, file_format)

                # Keep only the model resident between requests. Drop per-request
                # activations before accepting another inference request.
                del scene_codes, meshes
                gc.collect()
                if self._device and str(self._device).startswith("cuda"):
                    torch.cuda.empty_cache()

                import trimesh
                reloaded = trimesh.load(destination, force="mesh", process=False)
                return destination, {
                    "vertices": int(len(reloaded.vertices)),
                    "faces": int(len(reloaded.faces)),
                    "is_watertight": bool(reloaded.is_watertight),
                    "device": str(self._device),
                }
            except Exception:
                gc.collect()
                if self._torch is not None and self._device and str(self._device).startswith("cuda"):
                    self._torch.cuda.empty_cache()
                raise
