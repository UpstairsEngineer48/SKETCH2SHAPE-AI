"""
export.py
Helpers to serve generated mesh files as Flask responses.
"""

from pathlib import Path
from flask import send_file, jsonify


def serve_mesh(mesh_path: Path, filename: str = "model.glb"):
    """
    Return a Flask response that streams the mesh file to the client.

    Args:
        mesh_path: Absolute path to the .glb or .obj file.
        filename:  Download filename sent in Content-Disposition.
    """
    suffix   = Path(mesh_path).suffix.lower()
    mime_map = {
        ".glb": "model/gltf-binary",
        ".obj": "text/plain",
        ".gltf": "model/gltf+json",
    }
    mimetype = mime_map.get(suffix, "application/octet-stream")

    return send_file(
        mesh_path,
        mimetype=mimetype,
        as_attachment=False,          # inline so the viewer can fetch it
        download_name=filename,
    )


def error_response(message: str, status: int = 500):
    """Return a JSON error payload."""
    return jsonify({"error": message}), status
