"""Input preparation for the Hunyuan3D-2mini-Turbo ONNX DINOv2 graph.

The model expects RGB float32 NCHW [1,3,1022,1022] in [0,1], with the
subject centered on white and occupying roughly 85% of the frame.
Canny edges are generated as a diagnostic artifact only; they are NOT fed to
DINOv2 because the exported conditioner expects an RGB image.
"""
from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
import os

import cv2
import numpy as np
from PIL import Image, ImageOps

IMAGE_SIZE = 1022
TARGET_OBJECT_SIZE = int(IMAGE_SIZE * 0.85)


@dataclass
class PreprocessResult:
    model_image: Image.Image       # RGB 1022x1022 white canvas
    foreground_rgba: Image.Image   # cropped, transparent foreground
    edge_map: Image.Image          # grayscale diagnostic, not model input
    mask: Image.Image              # foreground mask
    method: str
    bbox: tuple[int, int, int, int] | None


def _decode(image_bytes: bytes) -> Image.Image:
    try:
        image = Image.open(BytesIO(image_bytes))
        image = ImageOps.exif_transpose(image)
        image.load()
        return image
    except Exception as exc:
        raise ValueError(f"Could not decode uploaded image: {exc}") from exc


def _rembg_cutout(image: Image.Image) -> Image.Image:
    """CPU background removal. Imported lazily so sketch-only mode stays light."""
    try:
        from rembg import new_session, remove
    except ImportError as exc:
        raise RuntimeError(
            "Background removal requested but rembg is not installed. "
            "Install with: pip install 'rembg[cpu]'"
        ) from exc

    # Cache one CPU session for the process. U2Net weights download on first use.
    global _REMBG_SESSION
    try:
        session = _REMBG_SESSION
    except NameError:
        session = None
    if session is None:
        session = new_session(os.getenv("REMBG_MODEL", "u2net"), providers=["CPUExecutionProvider"])
        _REMBG_SESSION = session
    rgba = image.convert("RGBA")
    result = remove(rgba, session=session)
    return result.convert("RGBA")


def _sketch_cutout(image: Image.Image) -> Image.Image:
    """Keep dark strokes and make near-white paper transparent; preserves line art."""
    rgb = image.convert("RGB")
    arr = np.asarray(rgb)
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    # Adaptive threshold tolerates uneven paper illumination better than a
    # single hard-coded RGB threshold. Dark strokes become opaque foreground.
    ink = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV, 31, 12
    )
    # Remove isolated speckles but avoid aggressive erosion of thin strokes.
    ink = cv2.morphologyEx(ink, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    # A small dilation restores continuity after denoising.
    ink = cv2.dilate(ink, np.ones((2, 2), np.uint8), iterations=1)
    alpha = ink
    rgba = np.dstack([arr, alpha])
    return Image.fromarray(rgba, "RGBA")


def _crop_alpha(rgba: Image.Image, margin_ratio: float = 0.04):
    alpha = np.asarray(rgba.getchannel("A"))
    ys, xs = np.where(alpha > 8)
    if len(xs) == 0:
        raise ValueError("No foreground subject detected. Try a clearer image or another input mode.")
    x0, x1 = int(xs.min()), int(xs.max()) + 1
    y0, y1 = int(ys.min()), int(ys.max()) + 1
    margin = max(4, int(max(x1 - x0, y1 - y0) * margin_ratio))
    x0, y0 = max(0, x0 - margin), max(0, y0 - margin)
    x1, y1 = min(rgba.width, x1 + margin), min(rgba.height, y1 + margin)
    return rgba.crop((x0, y0, x1, y1)), (x0, y0, x1, y1)


def _center_on_white(foreground: Image.Image) -> Image.Image:
    # Preserve aspect ratio, leave approximately 15% margin around the object.
    foreground = foreground.copy()
    foreground.thumbnail((TARGET_OBJECT_SIZE, TARGET_OBJECT_SIZE), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (IMAGE_SIZE, IMAGE_SIZE), (255, 255, 255, 255))
    x = (IMAGE_SIZE - foreground.width) // 2
    y = (IMAGE_SIZE - foreground.height) // 2
    canvas.alpha_composite(foreground, (x, y))
    return canvas.convert("RGB")


def preprocess_image(image_bytes: bytes, input_type: str = "auto", remove_background: bool = True) -> PreprocessResult:
    """Prepare photo or sketch. input_type is auto|photo|sketch.

    auto: use rembg when requested; otherwise use sketch/near-white extraction.
    photo: rembg is strongly recommended.
    sketch: adaptive threshold keeps ink strokes; rembg is deliberately avoided
    because segmentation models can erase thin lines.
    """
    image = _decode(image_bytes)
    if input_type not in {"auto", "photo", "sketch"}:
        raise ValueError("input_type must be auto, photo, or sketch")

    # For auto mode, infer whether the border resembles white sketch paper.
    # This is a lightweight heuristic, not semantic classification. Users can
    # override it with input_type=photo or input_type=sketch.
    has_alpha = image.mode in {"RGBA", "LA"} or (image.mode == "P" and "transparency" in image.info)
    detected_type = input_type
    if detected_type == "auto" and not has_alpha:
        rgb_probe = np.asarray(image.convert("RGB"))
        h, w = rgb_probe.shape[:2]
        border = np.concatenate([
            rgb_probe[:max(1, h // 20), :, :].reshape(-1, 3),
            rgb_probe[-max(1, h // 20):, :, :].reshape(-1, 3),
            rgb_probe[:, :max(1, w // 20), :].reshape(-1, 3),
            rgb_probe[:, -max(1, w // 20):, :].reshape(-1, 3),
        ], axis=0)
        detected_type = "sketch" if float(np.mean(np.min(border, axis=1) > 235)) > 0.55 else "photo"

    if has_alpha:
        cutout = image.convert("RGBA")
        method = "existing_alpha"
    elif detected_type == "sketch":
        cutout = _sketch_cutout(image)
        method = "adaptive_sketch_threshold"
    elif remove_background:
        cutout = _rembg_cutout(image)
        method = "rembg_cpu"
    else:
        raise ValueError("Photo input requires background removal. Set remove_background=true or provide an image with transparency.")

    cropped, bbox = _crop_alpha(cutout)
    model_image = _center_on_white(cropped)

    # Edge map is a quality-control/debug view. The model still receives RGB.
    gray = cv2.cvtColor(np.asarray(model_image), cv2.COLOR_RGB2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 50, 150)

    return PreprocessResult(
        model_image=model_image,
        foreground_rgba=cropped,
        edge_map=Image.fromarray(edges, mode="L"),
        mask=cropped.getchannel("A"),
        method=method,
        bbox=bbox,
    )


def prepare_dino_input(image_bytes: bytes, input_type: str = "auto", remove_background: bool = True) -> np.ndarray:
    """Return float32 NCHW [1,3,1022,1022], RGB [0,1].

    ImageNet mean/std are NOT applied because they are baked into this ONNX graph.
    """
    result = preprocess_image(image_bytes, input_type, remove_background)
    pixels = np.asarray(result.model_image, dtype=np.float32) / 255.0
    return np.transpose(pixels, (2, 0, 1))[None, ...].astype(np.float32)
