"""
background_removal.py
Cut the object out of the rendered image and frame it for the mesh model:
RGBA, square, object centred and filling ~85% of the frame.

Drop-in replacement for the original module:
    remove_background(input_path, output_path) -> Path

Designed not to crash. Every optional improvement (upscaling, alpha matting,
mask cleanup, colour de-fringing, the BiRefNet model) falls back to a simpler
step if it fails or if its dependency is missing. The only error raised on
purpose is ValueError when no object is found at all, same as the original.

Env vars (all optional)
  S2S_REMBG_MODEL   default birefnet-general (falls back to isnet-general-use, then u2net)
  S2S_MATTING       1 (default) alpha matting, 0 = off
  S2S_DEFRINGE      1 (default) colour de-fringing, 0 = off
  S2S_CLEAN         1 (default) mask cleanup, 0 = off
  S2S_UPSCALE_TO    default 1024, 0 = never upscale (only used while segmenting)
  S2S_ALPHA_LEVELS  1 (default) tighten the soft edge band, 0 = keep it as is
  S2S_DEBUG         1 = print which fallbacks were used
"""

import os
import threading
from pathlib import Path

import numpy as np
from PIL import Image

try:                      # optional: only needed for mask cleanup
    import cv2
except Exception:
    cv2 = None

DEFAULT_MODEL = "birefnet-general"
FALLBACK_MODELS = ("isnet-general-use", "u2net")

ALPHA_MIN = 16        # alpha at or below this counts as background
KEEP_FRAC = 0.08      # keep separate parts at least this fraction of the biggest part
HOLE_FRAC = 0.002     # fill enclosed holes smaller than this fraction of the object area
OPEN_KERNEL = 7       # opening size that snaps thin bridges to leftover blobs
EDGE_BLUR = 0.8       # gaussian sigma for edge anti-aliasing
MAX_WORK = 1536       # longest side kept for the colour pixels
LEVEL_LO, LEVEL_HI = 20, 225   # alpha below/above these snaps to 0/255

_sessions = {}
_session_lock = threading.Lock()


def _env_on(name, default="1"):
    return os.getenv(name, default) == "1"


def _log(msg):
    if _env_on("S2S_DEBUG", "0"):
        print(f"[background_removal] {msg}")


def _has_pymatting():
    try:
        import pymatting  # noqa: F401
        return True
    except Exception:
        return False


# --------------------------------------------------------------------------- #
# Model sessions
# --------------------------------------------------------------------------- #
def _get_session(name=None):
    """Create a rembg session once per model name. Raises if it cannot be loaded."""
    name = name or os.getenv("S2S_REMBG_MODEL", DEFAULT_MODEL)
    with _session_lock:
        if name not in _sessions:
            from rembg import new_session
            _sessions[name] = new_session(name)
        return _sessions[name]


def _model_chain():
    first = os.getenv("S2S_REMBG_MODEL", DEFAULT_MODEL)
    chain = [first] + [m for m in FALLBACK_MODELS if m != first]
    return chain


# --------------------------------------------------------------------------- #
# Steps
# --------------------------------------------------------------------------- #
def _maybe_upscale(img):
    """Upscale small inputs so the segmentation model sees more detail."""
    try:
        target = int(os.getenv("S2S_UPSCALE_TO", "1024"))
        longest = max(img.size)
        if target <= 0 or longest >= target:
            return img
        s = target / longest
        return img.resize((round(img.width * s), round(img.height * s)), Image.LANCZOS)
    except Exception as e:
        _log(f"upscale skipped: {e}")
        return img


def _cutout(img):
    """Segment the image. Tries each model, and each model with then without matting."""
    from rembg import remove

    matting_options = [True, False] if (_env_on("S2S_MATTING") and _has_pymatting()) else [False]
    last_err = None

    for name in _model_chain():
        try:
            session = _get_session(name)
        except Exception as e:
            _log(f"model '{name}' failed to load: {e}")
            last_err = e
            continue

        for matting in matting_options:
            try:
                kw = dict(session=session, post_process_mask=False)
                if matting:
                    kw.update(
                        alpha_matting=True,
                        alpha_matting_foreground_threshold=240,
                        alpha_matting_background_threshold=10,
                        alpha_matting_erode_size=10,
                    )
                out = remove(img, **kw).convert("RGBA")
                _log(f"segmented with '{name}', matting={matting}")
                return out
            except Exception as e:
                _log(f"model '{name}' matting={matting} failed: {e}")
                last_err = e

    raise RuntimeError(f"Background removal failed with every model: {last_err}")


def _fill_small_holes(mask, max_frac=HOLE_FRAC):
    """Fill small enclosed background pockets. Large holes (a mug handle) stay open."""
    inv = (mask == 0).astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(inv, connectivity=4)
    h, w = mask.shape
    limit = max_frac * float(mask.sum())
    out = mask.copy()
    for i in range(1, n):
        x, y, bw, bh, area = st[i]
        touches_border = x == 0 or y == 0 or x + bw >= w or y + bh >= h
        if not touches_border and area <= limit:
            out[lab == i] = 1
    return out


def _clean_impl(img):
    a = np.array(img.getchannel("A"))
    hard = (a > ALPHA_MIN).astype(np.uint8)

    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (OPEN_KERNEL, OPEN_KERNEL))
    opened = cv2.morphologyEx(hard, cv2.MORPH_OPEN, k)

    n, lab, st, _ = cv2.connectedComponentsWithStats(opened, connectivity=8)
    if n <= 1:
        return img
    areas = st[1:, cv2.CC_STAT_AREA]
    keep = np.flatnonzero(areas >= areas.max() * KEEP_FRAC) + 1
    keep_mask = np.isin(lab, keep).astype(np.uint8)

    keep_mask = cv2.dilate(keep_mask, k, iterations=1) & hard

    filled = _fill_small_holes(keep_mask)
    holes = (filled > 0) & (keep_mask == 0)

    a = np.where(filled > 0, a, 0).astype(np.uint8)
    a[holes] = 255
    a = cv2.erode(a, np.ones((2, 2), np.uint8))
    a = cv2.GaussianBlur(a, (0, 0), EDGE_BLUR)
    a[a <= ALPHA_MIN] = 0

    out = img.copy()
    out.putalpha(Image.fromarray(a))
    return out


def _clean(img):
    """Mask cleanup. Returns the input unchanged if opencv is missing or anything fails."""
    if cv2 is None or not _env_on("S2S_CLEAN"):
        return img
    try:
        out = _clean_impl(img)
        # never accept a cleanup that wipes out the object
        if out.getchannel("A").getbbox() is None:
            _log("cleanup removed everything, keeping original mask")
            return img
        return out
    except Exception as e:
        _log(f"cleanup skipped: {e}")
        return img


def _defringe(rgb_img, alpha_img):
    """Re-estimate edge colours from the original photo. Falls back to plain RGB + alpha."""
    plain = rgb_img.convert("RGBA")
    plain.putalpha(alpha_img)

    if not (_env_on("S2S_DEFRINGE") and _has_pymatting()):
        return plain
    try:
        from pymatting import estimate_foreground_ml
        rgb = np.asarray(rgb_img.convert("RGB"), dtype=np.float64) / 255.0
        a = np.asarray(alpha_img, dtype=np.float64) / 255.0
        fg = estimate_foreground_ml(rgb, a)
        out = np.dstack([np.clip(fg, 0, 1), a])
        return Image.fromarray((out * 255).round().astype(np.uint8), "RGBA")
    except Exception as e:
        _log(f"defringe skipped: {e}")
        return plain


def _levels(alpha):
    """Squeeze the soft edge band: near-transparent -> 0, near-opaque -> 255.

    A wide fuzzy band makes a ghostly halo and a mushy silhouette for the mesh model.
    """
    if not _env_on("S2S_ALPHA_LEVELS"):
        return alpha
    a = np.asarray(alpha, dtype=np.float32)
    a = np.clip((a - LEVEL_LO) / float(LEVEL_HI - LEVEL_LO), 0, 1) * 255
    return Image.fromarray(a.round().astype(np.uint8), "L")


def _frame_object(rgb, alpha, ratio=0.85, size=512):
    """Crop to the object, centre it on a transparent square, then fix edge colours.

    Works from the full-resolution colour image and a matching alpha, so the
    object is resized only once (down to the final frame) and stays sharp.
    """
    bbox = alpha.point(lambda a: 255 if a > ALPHA_MIN else 0).getbbox()
    if bbox is None:
        raise ValueError(
            "No object was found in the rendered image. "
            "Try a clearer sketch or a more specific prompt."
        )
    rgb_c, a_c = rgb.crop(bbox), alpha.crop(bbox)
    w, h = rgb_c.size
    scale = size * ratio / max(w, h)
    nw, nh = max(1, round(w * scale)), max(1, round(h * scale))
    rgb_c = rgb_c.resize((nw, nh), Image.LANCZOS)
    a_c = a_c.resize((nw, nh), Image.LANCZOS)

    pos = ((size - nw) // 2, (size - nh) // 2)
    rgb_canvas = Image.new("RGB", (size, size), (0, 0, 0))
    rgb_canvas.paste(rgb_c, pos)
    a_canvas = Image.new("L", (size, size), 0)
    a_canvas.paste(a_c, pos)
    return _defringe(rgb_canvas, a_canvas)     # cheap here: always <= 512x512


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def remove_background(input_path, output_path):
    """Remove the background, frame the object, save an RGBA PNG. Returns the output Path."""
    work = Image.open(input_path).convert("RGB")
    if max(work.size) > MAX_WORK:
        s = MAX_WORK / max(work.size)
        work = work.resize((round(work.width * s), round(work.height * s)), Image.LANCZOS)

    seg = _maybe_upscale(work)                  # upscaled copy is ONLY for segmentation
    cut = _clean(_cutout(seg))
    alpha = cut.getchannel("A")
    if alpha.size != work.size:
        alpha = alpha.resize(work.size, Image.LANCZOS)
    alpha = _levels(alpha)

    framed = _frame_object(work, alpha)         # colours come from the original pixels

    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    framed.save(out_path)
    return out_path


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        sys.exit("usage: python background_removal.py <in.png> [out.png]")
    src = Path(sys.argv[1])
    dst = Path(sys.argv[2]) if len(sys.argv) > 2 else src.with_name(src.stem + "_cutout.png")
    print(f"Background removed: {remove_background(src, dst)}")