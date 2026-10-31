"""
preprocessing.py
Turn a raw sketch or photo into a 512x512 control image for ControlNet.

The control image is white lines on a black background (what the Canny
ControlNet was trained on). It is built once here, so controlnet.py must
NOT run Canny again.
"""

import cv2
import numpy as np
from pathlib import Path
from PIL import Image


def _load_on_white(path):
    """Open an image and flatten any transparency onto white."""
    img=Image.open(path)
    if img.mode in("RGBA","LA","P"):
        img=img.convert("RGBA")
        bg=Image.new("RGBA",img.size,(255,255,255,255))
        bg.alpha_composite(img)
        img=bg
    return img.convert("RGB")


def _pad_square(img,fill=(255,255,255)):
    """Pad to a square without stretching the drawing."""
    w,h=img.size
    side=max(w,h)
    canvas=Image.new("RGB",(side,side),fill)
    canvas.paste(img,((side-w)//2,(side-h)//2))
    return canvas


def preprocess_sketch(input_path,output_path,size=512):
    """
    Build the ControlNet control image.

    Line drawings (mostly white paper, dark strokes) are thresholded and
    inverted so every stroke becomes ONE clean white line. Photos and
    shaded images use Canny edges instead.

    Returns (output_path,kind) where kind is "sketch" or "photo".
    """
    img=_pad_square(_load_on_white(input_path))
    gray=cv2.cvtColor(np.array(img),cv2.COLOR_RGB2GRAY)

    white_ratio=float((gray>200).mean())
    kind="sketch" if white_ratio>0.6 else "photo"

    if kind=="sketch":
        # Thin pen lines vanish when a big canvas is shrunk to 512px,
        # so thicken the dark pixels a little before resizing.
        k=max(1,gray.shape[0]//size)
        if k>1:
            gray=cv2.erode(gray,np.ones((k,k),np.uint8))
        gray=cv2.resize(gray,(size,size),interpolation=cv2.INTER_AREA)
        _,lines=cv2.threshold(gray,0,255,cv2.THRESH_BINARY_INV+cv2.THRESH_OTSU)
        lines=cv2.dilate(lines,np.ones((2,2),np.uint8))
    else:
        gray=cv2.resize(gray,(size,size),interpolation=cv2.INTER_AREA)
        blur=cv2.GaussianBlur(gray,(5,5),0)
        lines=cv2.Canny(blur,100,200)

    if (lines>0).mean()<0.001:
        raise ValueError("The sketch looks empty. Draw something with darker, thicker lines.")

    Image.fromarray(np.stack([lines]*3,axis=-1)).save(output_path)
    return Path(output_path),kind
