"""
background_removal.py
Cut the object out of the rendered image and frame it the way InstantMesh
expects: RGBA, square, object centred and filling ~85% of the frame.
"""

import os
import threading
from pathlib import Path

from PIL import Image

_session=None
_session_lock=threading.Lock()


def _get_session():
    """Create the rembg session once. Re-creating it per call reloads the model."""
    global _session
    with _session_lock:
        if _session is None:
            from rembg import new_session
            _session=new_session(os.getenv("S2S_REMBG_MODEL","u2net"))
        return _session


def _frame_object(img,ratio=0.85,size=512):
    """Crop to the object's bounding box and centre it on a transparent square."""
    bbox=img.getchannel("A").point(lambda a:255 if a>16 else 0).getbbox()
    if bbox is None:
        raise ValueError("No object was found in the rendered image. Try a clearer sketch or a more specific prompt.")
    obj=img.crop(bbox)
    w,h=obj.size
    scale=size*ratio/max(w,h)
    obj=obj.resize((max(1,round(w*scale)),max(1,round(h*scale))),Image.LANCZOS)
    canvas=Image.new("RGBA",(size,size),(0,0,0,0))
    canvas.paste(obj,((size-obj.width)//2,(size-obj.height)//2),obj)
    return canvas


def remove_background(input_path,output_path):
    """Remove the background, frame the object, save an RGBA PNG."""
    from rembg import remove
    image=Image.open(input_path).convert("RGB")
    cutout=remove(image,session=_get_session()).convert("RGBA")
    _frame_object(cutout).save(output_path)
    return Path(output_path)
