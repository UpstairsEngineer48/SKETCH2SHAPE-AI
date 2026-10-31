from pathlib import Path

import numpy as np
import trimesh
from PIL import Image, ImageDraw

from app.export import export_mesh
from app.preprocessing import prepare_image


def test_draw_preprocessing_returns_centered_square_rgb():
    sketch = Image.new("RGB", (1400, 900), "white")
    draw = ImageDraw.Draw(sketch)
    draw.rectangle((350, 200, 1050, 700), outline="black", width=18)

    prepared = prepare_image(sketch, input_type="draw")

    assert prepared.mode == "RGB"
    assert prepared.size == (512, 512)
    assert np.asarray(prepared).std() > 0


def test_blank_sketch_is_rejected():
    blank = Image.new("RGB", (1400, 900), "white")

    try:
        prepare_image(blank, input_type="draw")
    except ValueError as exc:
        assert "blank" in str(exc).lower()
    else:
        raise AssertionError("A blank sketch should be rejected.")


def test_mesh_exports_as_real_glb_and_can_be_reloaded(tmp_path: Path):
    mesh = trimesh.creation.icosphere(subdivisions=2, radius=1.0)
    mesh.visual.vertex_colors = [180, 110, 220, 255]

    output = export_mesh(mesh, tmp_path / "test.glb", "glb")
    loaded = trimesh.load(output, force="mesh", process=False)

    assert output.exists()
    assert len(loaded.vertices) > 0
    assert len(loaded.faces) > 0
    assert float(loaded.extents.max()) > 0


def test_uploaded_white_paper_sketch_is_detected_and_conditioned():
    sketch = Image.new("RGB", (640, 480), "white")
    draw = ImageDraw.Draw(sketch)
    draw.ellipse((170, 80, 470, 400), outline=(35, 35, 35), width=12)

    prepared = prepare_image(sketch, input_type="upload")

    assert prepared.size == (512, 512)
    assert np.asarray(prepared).std() > 0
