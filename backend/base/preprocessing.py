"""
preprocessing.py
Turn a raw sketch or photo into a 512x512 control image for ControlNet.

The control image is white lines on a black background (what the Canny
ControlNet was trained on). It is built once here, so controlnet.py must
NOT run Canny again.
"""

import os
import cv2
import numpy as np
from pathlib import Path
from PIL import Image

# Canny thresholds, tried in order until the edge map has enough detail.
# The first pair is the old fixed setting, so images that already worked
# (strong edges) give exactly the same control image as before.
CANNY_LADDER=((100,200),(75,150),(55,110),(40,80),(28,56),(18,36))
MIN_EDGE_DENSITY=0.015          # fraction of pixels that should be edge
SKETCH_CROP=os.getenv("S2S_SKETCH_CROP","1")=="1"   # re-frame small drawings


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


def load_photo(path,max_side=1536):
    """Photo at its ORIGINAL resolution (only shrunk if huge). No padding."""
    img=_load_on_white(path)
    w,h=img.size
    s=max(w,h)
    if s>max_side:
        img=img.resize((round(w*max_side/s),round(h*max_side/s)),Image.LANCZOS)
    return img


def _photo_edges(img,size):
    """Canny edges of a photo. Relaxes the thresholds when the photo is soft.

    The photo is padded to a square by replicating its border (not with white),
    otherwise the padding itself creates straight fake edges.
    """
    arr=np.array(img)
    h,w=arr.shape[:2]
    s=max(h,w)
    top,left=(s-h)//2,(s-w)//2
    arr=cv2.copyMakeBorder(arr,top,s-h-top,left,s-w-left,cv2.BORDER_REPLICATE)
    gray=cv2.cvtColor(arr,cv2.COLOR_RGB2GRAY)
    gray=cv2.resize(gray,(size,size),interpolation=cv2.INTER_AREA)
    blur=cv2.GaussianBlur(gray,(5,5),0)
    edges=None
    for lo,hi in CANNY_LADDER:
        edges=cv2.Canny(blur,lo,hi)
        if (edges>0).mean()>=MIN_EDGE_DENSITY:
            break
    # replicated padding makes streaky fake edges: blank everything outside the photo
    f=size/s
    inside=np.zeros_like(edges)
    inside[int(top*f):int(np.ceil((top+h)*f)),int(left*f):int(np.ceil((left+w)*f))]=255
    return cv2.bitwise_and(edges,inside)


def _sketch_lines(gray,size):
    """Dark strokes -> white lines. gray may be any aspect; long side becomes `size`."""
    h,w=gray.shape
    k=max(1,max(h,w)//size)
    if k>1:
        # thin pen lines vanish when a big canvas is shrunk, so thicken first
        gray=cv2.erode(gray,np.ones((k,k),np.uint8))
    scale=size/max(h,w)
    gray=cv2.resize(gray,(max(8,round(w*scale)),max(8,round(h*scale))),interpolation=cv2.INTER_AREA)
    _,lines=cv2.threshold(gray,0,255,cv2.THRESH_BINARY_INV+cv2.THRESH_OTSU)
    return cv2.dilate(lines,np.ones((2,2),np.uint8))


def _reframe_sketch(gray_full,lines0,size,margin=0.06,min_side=256):
    """Crop to the drawing, scale it to fill the canvas, keep its aspect ratio.

    A small drawing in a big empty canvas gives the image model very little to
    work with. The crop is cut from the ORIGINAL pixels (not from the 512px
    lines) so the stroke thickness stays natural. Output sides are multiples
    of 8, as Stable Diffusion needs.
    """
    n,_,st,_=cv2.connectedComponentsWithStats((lines0>0).astype(np.uint8),connectivity=8)
    keep=[i for i in range(1,n) if st[i,cv2.CC_STAT_AREA]>=10]
    if not keep:
        return lines0
    x0=min(st[i,cv2.CC_STAT_LEFT] for i in keep)
    y0=min(st[i,cv2.CC_STAT_TOP] for i in keep)
    x1=max(st[i,cv2.CC_STAT_LEFT]+st[i,cv2.CC_STAT_WIDTH] for i in keep)
    y1=max(st[i,cv2.CC_STAT_TOP]+st[i,cv2.CC_STAT_HEIGHT] for i in keep)
    side=lines0.shape[0]
    if (x1-x0)>=0.8*side and (y1-y0)>=0.8*side:
        return lines0                      # already fills the frame
    m=int(margin*max(x1-x0,y1-y0))+2
    f=gray_full.shape[0]/side              # 512px coords -> original pixels
    X0,Y0=max(0,int((x0-m)*f)),max(0,int((y0-m)*f))
    X1,Y1=min(gray_full.shape[1],int((x1+m)*f)),min(gray_full.shape[0],int((y1+m)*f))
    lines=_sketch_lines(gray_full[Y0:Y1,X0:X1],size)
    h,w=lines.shape
    H=max(min_side,h)
    W=max(min_side,w)
    H+=(-H)%8
    W+=(-W)%8
    canvas=np.zeros((H,W),np.uint8)
    canvas[(H-h)//2:(H-h)//2+h,(W-w)//2:(W-w)//2+w]=lines
    return canvas


def classify(img,gray):
    """"sketch" = flat drawing on paper, "photo" = everything else.

    A drawing is almost all paper plus a handful of flat ink colours, so a few
    colour buckets hold nearly every pixel. A photo spreads over hundreds.
    (An earlier version counted coloured pixels instead, and a thick dark-blue
    brush stroke was mistaken for a photo.)
    """
    arr=np.array(img)
    white=float((gray>200).mean())
    mid=float(((gray>40)&(gray<215)).mean())
    q=(arr//16).astype(np.int32)
    key=q[...,0]*256+q[...,1]*16+q[...,2]
    counts=np.sort(np.bincount(key.ravel()))[::-1]
    top4=float(counts[:4].sum())/float(key.size)
    return "sketch" if(white>0.8 and mid<0.15 and top4>0.9)else "photo"


def preprocess_sketch(input_path,output_path,size=512,force_kind=None):
    """
    Build the ControlNet control image.

    Line drawings (mostly white paper, dark strokes) are thresholded and
    inverted so every stroke becomes ONE clean white line. Photos and
    shaded images use Canny edges instead.

    force_kind="sketch"/"photo" skips the guess (the UI knows when the user
    drew on the canvas).

    Returns (output_path,kind) where kind is "sketch" or "photo".
    """
    base=_load_on_white(input_path)
    img=_pad_square(base)
    gray=cv2.cvtColor(np.array(img),cv2.COLOR_RGB2GRAY)

    kind=force_kind if force_kind in("sketch","photo") else classify(img,gray)

    if kind=="sketch":
        lines=_sketch_lines(gray,size)
        if SKETCH_CROP:
            lines=_reframe_sketch(gray,lines,size)
    else:
        lines=_photo_edges(base,size)

    if (lines>0).mean()<0.001:
        raise ValueError("The sketch looks empty. Draw something with darker, thicker lines.")

    Image.fromarray(np.stack([lines]*3,axis=-1)).save(output_path)
    return Path(output_path),kind