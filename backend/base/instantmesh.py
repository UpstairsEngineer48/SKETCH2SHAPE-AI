"""
instantmesh.py
Calls the TencentARC/InstantMesh HuggingFace Space through gradio_client.

Input : RGBA PNG of one centred object (background already removed)
Output: a .glb (or .obj) mesh saved in the job folder

Set HF_TOKEN (a free Hugging Face access token) to get a much larger
ZeroGPU quota than anonymous callers. Without it the Space often rejects
or queues requests.
"""

import inspect
import logging
import os
import shutil
from pathlib import Path

from gradio_client import Client,handle_file

log=logging.getLogger(__name__)

SPACE_ID=os.getenv("S2S_INSTANTMESH_SPACE","TencentARC/InstantMesh")
DEFAULT_STEPS=int(os.getenv("S2S_MVS_STEPS","50"))   # Space default is 75; 30-75 allowed


def _make_client():
    token=os.getenv("HF_TOKEN") or None
    kwargs={}
    if token:
        # gradio_client renamed hf_token -> token in newer releases
        params=inspect.signature(Client.__init__).parameters
        kwargs["token" if "token" in params else "hf_token"]=token
    else:
        log.warning("HF_TOKEN is not set - the InstantMesh Space may reject you for GPU quota.")
    return Client(SPACE_ID,**kwargs)


def _flatten(value):
    """Yield every string path found anywhere inside a (nested) client result."""
    if isinstance(value,(list,tuple)):
        for item in value:
            yield from _flatten(item)
    elif isinstance(value,dict):
        for item in value.values():
            yield from _flatten(item)
    elif isinstance(value,(str,os.PathLike)):
        yield str(value)


def pick_mesh(result):
    """
    make3d returns several outputs (video, .obj, .glb ...). Don't trust the
    position - choose by file extension. Prefers .glb, falls back to .obj.
    """
    paths=list(_flatten(result))
    for ext in(".glb",".obj"):
        for p in paths:
            if p.lower().endswith(ext):
                return Path(p)
    raise RuntimeError(f"InstantMesh returned no .glb/.obj file. Got: {paths}")


def _as_file(value):
    if isinstance(value,str) and Path(value).exists():
        return handle_file(value)
    return value


def run_instantmesh(input_image_path,output_dir,sample_steps=None,sample_seed=42,on_stage=None):
    """
    Run InstantMesh on one image.

    Returns the path of the saved mesh (model.glb, or model.obj as a fallback).
    on_stage(text) is called before each remote step so the UI can show progress.
    """
    say=on_stage or(lambda _:None)
    steps=sample_steps or DEFAULT_STEPS
    output_dir=Path(output_dir)
    output_dir.mkdir(parents=True,exist_ok=True)

    say("Connecting to InstantMesh")
    client=_make_client()   # one client = one session; make3d reads state saved by generate_mvs

    say("Preparing the image")
    processed=client.predict(handle_file(str(input_image_path)),False,api_name="/preprocess")

    say("Generating multi-view images (slowest step)")
    client.predict(_as_file(processed),steps,sample_seed,api_name="/generate_mvs")

    say("Reconstructing the 3D mesh")
    result=client.predict(api_name="/make3d")

    mesh=pick_mesh(result)
    target=output_dir/f"model{mesh.suffix.lower()}"
    shutil.copy(mesh,target)
    log.info("Mesh saved: %s",target)
    return target
