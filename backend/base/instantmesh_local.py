"""
instantmesh_local.py
Local image -> 3D mesh with the official InstantMesh repo (its run.py).

Input : RGBA PNG of one centred object (background already removed)
Output: model.glb in the job folder (model.obj if the conversion step fails)

Like Hunyuan3D it runs in a SEPARATE process: InstantMesh pins its own torch /
diffusers versions and builds nvdiffrast, so it needs its own environment.
It needs an NVIDIA GPU (InstantMesh's run.py is CUDA only).

Env:
  S2S_IM_DIR      folder of the cloned InstantMesh repo. Not set = backend is skipped
  S2S_IM_PYTHON   python(.exe) of the InstantMesh env (default: the backend's python)
  S2S_IM_CONFIG   config relative to S2S_IM_DIR (default configs/instant-mesh-large.yaml,
                  configs/instant-mesh-base.yaml is the lighter one)
  S2S_MVS_STEPS   multi-view steps, same variable as the API route (default 50)
  S2S_IM_SEED     default S2S_SEED, then 42
"""

import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

from base import cancel
from base.mesh import Unavailable

log=logging.getLogger(__name__)

IM_DIR=os.getenv("S2S_IM_DIR","").strip()
PY=os.getenv("S2S_IM_PYTHON") or sys.executable
CONFIG=os.getenv("S2S_IM_CONFIG","configs/instant-mesh-large.yaml")
STEPS=int(os.getenv("S2S_MVS_STEPS","50"))
SEED=int(os.getenv("S2S_IM_SEED",os.getenv("S2S_SEED","42")))
CONVERT=Path(__file__).with_name("im_to_glb.py")

# lines printed by run.py -> label for the UI
STAGES=(("] Imagining ","Generating multi-view images (slowest step)"),("] Creating ","Reconstructing the 3D mesh"))


def _root():
    if not IM_DIR:
        raise Unavailable("InstantMesh (local) is not set up: set S2S_IM_DIR to your InstantMesh clone (see README).")
    root=Path(IM_DIR)
    if not (root/"run.py").is_file():
        raise Unavailable(f"InstantMesh (local): no run.py in S2S_IM_DIR={root}")
    if not (root/CONFIG).is_file():
        raise Unavailable(f"InstantMesh (local): config not found: {root/CONFIG}")
    return root


def _run(cmd,cwd,on_line,job=None):
    """Runs a command, echoes its output to the backend terminal. Returns (exit code, last lines)."""
    env=dict(os.environ,PYTHONUNBUFFERED="1",PYTHONIOENCODING="utf-8")
    proc=subprocess.Popen(cmd,cwd=cwd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding="utf-8",errors="replace",env=env)
    if job:
        cancel.track(job,proc)
    tail=[]
    for line in proc.stdout:
        print(line,end="",flush=True)
        log.debug("[im] %s",line.rstrip())
        tail=(tail+[line.rstrip()[:200]+"\n"])[-15:]
        on_line(line)
    proc.wait()
    return proc.returncode,"".join(tail)[-600:]


def run_instantmesh_local(input_image_path,output_dir,on_stage=None,seed=None):
    """Returns the path of the saved mesh. on_stage(text) updates the UI label."""
    say=on_stage or(lambda _:None)
    root=_root()
    out=Path(output_dir)
    out.mkdir(parents=True,exist_ok=True)

    work=out/"im_work"
    shutil.rmtree(work,ignore_errors=True)
    work.mkdir()
    src=work/"input.png"   # fixed name: run.py names its result after the input file
    shutil.copy(input_image_path,src)

    say("Starting InstantMesh locally (first run downloads the models, see the backend terminal)")
    # --no_rembg: the cutout is already done (same input the API route gets)
    cmd=[PY,"-u","run.py",CONFIG,str(src),"--output_path",str(work/"out"),"--diffusion_steps",str(STEPS),"--seed",str(SEED if seed is None else seed),"--no_rembg"]

    def on_line(line):
        for key,text in STAGES:
            if key in line:
                say(text)

    code,tail=_run(cmd,root,on_line,out.name)
    obj=work/"out"/Path(CONFIG).stem/"meshes"/"input.obj"
    if code!=0 or not obj.exists():
        raise RuntimeError("InstantMesh (local) failed: "+tail)

    say("Converting the mesh to GLB")
    glb=out/"model.glb"
    code,tail=_run([PY,str(CONVERT),str(obj),str(glb)],root,lambda _:None)
    if code==0 and glb.exists():
        mesh=glb
    else:
        # the mesh is fine, only its orientation differs from the API route
        log.warning("GLB conversion failed, returning the raw .obj. %s",tail)
        mesh=out/"model.obj"
        shutil.copy(obj,mesh)
    shutil.rmtree(work,ignore_errors=True)
    log.info("Mesh saved: %s",mesh)
    return mesh