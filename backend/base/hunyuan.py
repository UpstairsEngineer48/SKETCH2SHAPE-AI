"""
hunyuan.py
Local image -> 3D mesh with Hunyuan3D-2mini (shape only, no texture).

Input : RGBA PNG of one centred object (background already removed)
Output: model.glb in the job folder

The model runs in a SEPARATE process (hy_worker.py). That keeps its pinned
dependencies away from the backend env and gives every byte of VRAM back
when it exits. Point S2S_HY_PYTHON at the python.exe of the Hunyuan3D env.
If it is not set, the backend's own python is used.
"""

import logging
import os
import subprocess
import sys
from pathlib import Path

log=logging.getLogger(__name__)

PY=os.getenv("S2S_HY_PYTHON") or sys.executable
WORKER=Path(__file__).with_name("hy_worker.py")


def run_hunyuan(input_image_path,output_dir,on_stage=None):
    """Returns the path of the saved model.glb. on_stage(text) updates the UI label."""
    say=on_stage or(lambda _:None)
    out=Path(output_dir)
    out.mkdir(parents=True,exist_ok=True)
    target=out/"model.glb"

    say("Generating the 3D shape (first run downloads the model, see the backend terminal)")
    env=dict(os.environ,PYTHONUNBUFFERED="1",PYTHONIOENCODING="utf-8")
    proc=subprocess.Popen([PY,"-u",str(WORKER),str(input_image_path),str(target)],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding="utf-8",errors="replace",env=env)
    tail=[]
    for line in proc.stdout:
        print(line,end="",flush=True)
        tail=(tail+[line[:200]+"\n"])[-15:]
    proc.wait()
    if proc.returncode!=0 or not target.exists():
        raise RuntimeError("Hunyuan3D failed: "+"".join(tail)[-600:])
    log.info("Mesh saved: %s",target)
    return target