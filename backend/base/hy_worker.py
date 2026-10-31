"""
hy_worker.py
Runs inside the Hunyuan3D environment (started by hunyuan.py).

  python hy_worker.py <rgba_image> <out.glb>

Shape only (no texture), so nothing has to be compiled.
Env (all optional): S2S_HY_MODEL, S2S_HY_SUB, S2S_HY_STEPS, S2S_HY_OCT, S2S_HY_CHUNKS, S2S_HY_SEED
"""

import os
import sys

import torch
from PIL import Image
from hy3dgen.shapegen import Hunyuan3DDiTFlowMatchingPipeline

MODEL=os.getenv("S2S_HY_MODEL","tencent/Hunyuan3D-2mini")
SUB=os.getenv("S2S_HY_SUB","hunyuan3d-dit-v2-mini")
STEPS=int(os.getenv("S2S_HY_STEPS","30"))
OCT=int(os.getenv("S2S_HY_OCT","256"))        # mesh detail; lower = less VRAM
CHUNKS=int(os.getenv("S2S_HY_CHUNKS","8000")) # smaller chunks = lower VRAM peak
SEED=int(os.getenv("S2S_HY_SEED","42"))


def main(src,dst):
    dev="cuda" if torch.cuda.is_available() else "cpu"
    if dev=="cpu":
        print("WARNING: no CUDA GPU found, this will be very slow",file=sys.stderr)
    print("[hy] loading model (downloads on first run)",flush=True)
    pipe=Hunyuan3DDiTFlowMatchingPipeline.from_pretrained(MODEL,subfolder=SUB,use_safetensors=True,device=dev)
    print("[hy] model ready, generating on "+dev,flush=True)
    img=Image.open(src).convert("RGBA")
    mesh=pipe(image=img,num_inference_steps=STEPS,octree_resolution=OCT,num_chunks=CHUNKS,generator=torch.manual_seed(SEED),output_type="trimesh")[0]
    mesh.export(dst)
    print("[hy] done",flush=True)


if __name__=="__main__":
    main(sys.argv[1],sys.argv[2])