"""Input validation and normalization for single-image 3D reconstruction."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import numpy as np
from PIL import Image, ImageOps

INPUT_SIZE = 512


def is_white_paper_sketch(image: Image.Image) -> bool:
    """Heuristic for uploaded line drawings on white paper."""
    rgb = np.asarray(image.convert("RGB"), dtype=np.uint8)
    gray = np.asarray(image.convert("L"), dtype=np.uint8)
    h, w = gray.shape
    border_width = max(2, min(h, w) // 40)
    border = np.concatenate([
        gray[:border_width, :].ravel(),
        gray[-border_width:, :].ravel(),
        gray[:, :border_width].ravel(),
        gray[:, -border_width:].ravel(),
    ])
    saturation = rgb.max(axis=2).astype(np.int16) - rgb.min(axis=2).astype(np.int16)
    white_fraction = float(np.mean(gray > 235))
    return (
        float(np.median(border)) > 230
        and float(np.mean(saturation)) < 48
        and white_fraction > 0.50
    )


def _white_background_to_alpha(image: Image.Image) -> Image.Image:
    """Turn a white sketch-paper background into transparency.

    This is used for the application's white drawing canvas and detected
    white-paper line drawings. It is not intended for photographs.
    """
    rgb = np.asarray(image.convert("RGB"), dtype=np.float32)
    distance_from_white = np.linalg.norm(255.0 - rgb, axis=2)

    # Ignore tiny compression / antialiasing noise while retaining pale pencil
    # strokes. The ramp makes antialiased line edges partially transparent.
    alpha = np.clip((distance_from_white - 7.0) / 52.0 * 255.0, 0, 255)
    rgba = np.dstack([rgb.clip(0, 255).astype(np.uint8), alpha.astype(np.uint8)])
    return Image.fromarray(rgba, mode="RGBA")


def _crop_to_foreground(image: Image.Image, padding: float = 0.10) -> Image.Image:
    rgba = image.convert("RGBA")
    alpha = np.asarray(rgba.getchannel("A"))
    ys, xs = np.where(alpha > 8)
    if len(xs) == 0 or len(ys) == 0:
        raise ValueError("The sketch appears blank. Draw or upload a visible object first.")

    left, right = int(xs.min()), int(xs.max()) + 1
    top, bottom = int(ys.min()), int(ys.max()) + 1
    width, height = right - left, bottom - top
    pad_x = max(8, int(width * padding))
    pad_y = max(8, int(height * padding))
    left = max(0, left - pad_x)
    top = max(0, top - pad_y)
    right = min(rgba.width, right + pad_x)
    bottom = min(rgba.height, bottom + pad_y)
    return rgba.crop((left, top, right, bottom))


def prepare_image(
    image: Image.Image,
    input_type: Literal["draw", "upload"] = "upload",
    image_size: int = INPUT_SIZE,
    foreground_ratio: float = 0.82,
) -> Image.Image:
    """Normalize an input image to a centered RGB square for TripoSR.

    Drawn canvas images and detected white-paper line drawings have their
    background removed using a luminance-based mask. Transparent uploads retain
    their alpha channel; photographs retain their background unless optional
    rembg preprocessing is enabled by the API.
    """
    if image is None:
        raise ValueError("No image was supplied.")
    if image.width < 2 or image.height < 2:
        raise ValueError("The supplied image is too small to reconstruct.")

    image = ImageOps.exif_transpose(image)
    has_alpha = "A" in image.getbands() or "transparency" in image.info
    alpha_has_transparency = False
    if has_alpha:
        alpha_channel = np.asarray(image.convert("RGBA").getchannel("A"))
        alpha_has_transparency = bool(np.any(alpha_channel < 250))

    if (input_type == "draw" or is_white_paper_sketch(image)) and not alpha_has_transparency:
        # The browser canvas PNG may contain an all-opaque alpha channel. Treat
        # it as paper, not as a meaningful transparency mask.
        foreground = _white_background_to_alpha(image)
    elif has_alpha:
        foreground = image.convert("RGBA")
    else:
        foreground = image.convert("RGB").convert("RGBA")

    foreground = _crop_to_foreground(foreground)

    # Fit the foreground into a square canvas while retaining its aspect ratio.
    target_extent = max(32, min(image_size, int(image_size * foreground_ratio)))
    fitted = ImageOps.contain(
        foreground,
        (target_extent, target_extent),
        method=Image.Resampling.LANCZOS,
    )
    canvas = Image.new("RGBA", (image_size, image_size), (128, 128, 128, 255))
    position = ((image_size - fitted.width) // 2, (image_size - fitted.height) // 2)
    canvas.alpha_composite(fitted, dest=position)
    return canvas.convert("RGB")


def validate_image_bytes(data: bytes, max_bytes: int) -> None:
    if not data:
        raise ValueError("The uploaded image is empty.")
    if len(data) > max_bytes:
        raise ValueError(f"Image exceeds the {max_bytes // (1024 * 1024)} MB upload limit.")


def save_prepared_image(image: Image.Image, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG", optimize=True)
    return path
