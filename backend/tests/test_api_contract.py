from io import BytesIO
from pathlib import Path
import shutil

from fastapi.testclient import TestClient
from PIL import Image, ImageDraw
import trimesh

import app.main as api
from app.export import export_mesh


def test_generate_upload_returns_a_served_glb_without_loading_the_neural_model(monkeypatch):
    def fake_generate(image, output_path, file_format="glb", mesh_resolution=256):
        mesh = trimesh.creation.icosphere(subdivisions=1, radius=1.0)
        mesh.visual.vertex_colors = [120, 160, 220, 255]
        output = export_mesh(mesh, output_path, file_format)
        return output, {
            "vertices": len(mesh.vertices),
            "faces": len(mesh.faces),
            "is_watertight": bool(mesh.is_watertight),
            "device": "test-stub",
        }

    monkeypatch.setattr(api.reconstructor, "generate", fake_generate)

    sketch = Image.new("RGB", (400, 300), "white")
    draw = ImageDraw.Draw(sketch)
    draw.rectangle((100, 50, 300, 250), outline="black", width=8)
    buffer = BytesIO()
    sketch.save(buffer, format="PNG")

    job_dir: Path | None = None
    try:
        with TestClient(api.app) as client:
            response = client.post(
                "/generate",
                files={"image": ("sketch.png", buffer.getvalue(), "image/png")},
                data={"input_type": "draw", "prompt": "a wooden cabinet"},
            )
            assert response.status_code == 200
            payload = response.json()
            assert payload["format"] == "glb"
            assert payload["prompt_used"] is False
            assert payload["mesh"]["vertices"] > 0

            job_dir = Path(api.OUTPUT_DIR) / payload["job_id"]
            asset_response = client.get(payload["model_url"])
            assert asset_response.status_code == 200
            assert asset_response.headers["content-type"] == "model/gltf-binary"
            assert len(asset_response.content) > 128
    finally:
        if job_dir and job_dir.exists():
            shutil.rmtree(job_dir)
