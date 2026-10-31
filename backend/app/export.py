"""3D mesh export and validation utilities."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import trimesh


class MeshValidationError(RuntimeError):
    """Raised when a reconstructed asset is empty or malformed."""


def as_trimesh(mesh_or_scene) -> trimesh.Trimesh:
    if isinstance(mesh_or_scene, trimesh.Scene):
        if not mesh_or_scene.geometry:
            raise MeshValidationError("The reconstruction returned an empty scene.")
        mesh = mesh_or_scene.to_geometry()
    elif isinstance(mesh_or_scene, trimesh.Trimesh):
        mesh = mesh_or_scene
    else:
        raise MeshValidationError(
            f"Unsupported reconstruction mesh type: {type(mesh_or_scene).__name__}"
        )

    if len(mesh.vertices) == 0 or len(mesh.faces) == 0:
        raise MeshValidationError("The reconstructed mesh contains no vertices or faces.")
    if not np.isfinite(np.asarray(mesh.vertices)).all():
        raise MeshValidationError("The reconstructed mesh contains invalid coordinates.")
    if not np.isfinite(np.asarray(mesh.faces)).all():
        raise MeshValidationError("The reconstructed mesh contains invalid face indices.")

    extents = np.asarray(mesh.extents, dtype=float)
    if extents.size != 3 or not np.isfinite(extents).all() or float(extents.max()) <= 1e-8:
        raise MeshValidationError("The reconstructed mesh has no measurable 3D extent.")
    return mesh


def export_mesh(mesh_or_scene, output_path: str | Path, file_format: str = "glb") -> Path:
    """Export a real mesh as GLB or OBJ, then reload it for validation."""
    file_format = file_format.lower().lstrip(".")
    if file_format not in {"glb", "obj"}:
        raise ValueError("Only GLB and OBJ exports are supported.")

    mesh = as_trimesh(mesh_or_scene)
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    mesh.export(destination, file_type=file_format)

    if not destination.exists() or destination.stat().st_size < 128:
        raise MeshValidationError("The exported 3D file is missing or unexpectedly small.")

    loaded = trimesh.load(destination, force="mesh", process=False)
    as_trimesh(loaded)
    return destination
