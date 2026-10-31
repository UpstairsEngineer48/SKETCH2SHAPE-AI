"""Optional background-removal helper. Safe to import; no work runs at import."""

from __future__ import annotations

from PIL import Image

_SESSION = None


def remove_background_image(image: Image.Image) -> Image.Image:
    """Return an RGBA image with the background removed using rembg."""
    global _SESSION
    try:
        from rembg import new_session, remove
    except ImportError as exc:
        raise RuntimeError(
            "Photo background removal requires the optional 'rembg' package. "
            "Install the upstream TripoSR requirements or disable it with REMOVE_BACKGROUND_UPLOADS=0."
        ) from exc

    if _SESSION is None:
        _SESSION = new_session()
    result = remove(image.convert("RGBA"), session=_SESSION)
    return result.convert("RGBA")
