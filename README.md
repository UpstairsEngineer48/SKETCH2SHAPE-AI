# Sketch2Shape AI

Sketch -> ControlNet render -> background removal -> 3D mesh (Hunyuan3D or InstantMesh) -> GLB viewer.

## Run it

**Backend** (terminal 1)

```
cd backend
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate

# NVIDIA GPU? install the CUDA torch FIRST (pick your CUDA version on pytorch.org):
pip install torch --index-url https://download.pytorch.org/whl/cu121

pip install -r ../requirements.txt

set HF_TOKEN=hf_xxxxxxxx          # PowerShell: $env:HF_TOKEN="hf_xxx"  |  bash: export HF_TOKEN=hf_xxx
python app.py
```

**Frontend** (terminal 2)

```
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. The status light in the top bar turns green when
the model is loaded. The first start downloads several GB of weights.

## Why it can be slow

| Cause | Fix |
|---|---|
| torch installed without CUDA (log says `No CUDA GPU detected`) | reinstall torch with the CUDA index URL above |
| No `HF_TOKEN`: the shared InstantMesh Space queues or rejects you | create a free token at huggingface.co/settings/tokens |
| GPU with little VRAM | start with `S2S_LOW_VRAM=1` |

On CPU the app switches to a fast 6-step sampler automatically (`S2S_FAST=auto`).
Force it with `S2S_FAST=1`, or turn it off with `S2S_FAST=0` for slightly better quality.

## Settings (environment variables)

| Variable | Default | Meaning |
|---|---|---|
| `HF_TOKEN` | none | Hugging Face token for the InstantMesh Space |
| `S2S_MESH` | `hunyuan,instantmesh_local,instantmesh_api` | 3D backends, in the order they are tried (see below) |
| `S2S_HY_PYTHON` | backend python | `python.exe` of the Hunyuan3D env |
| `S2S_HY_OCT` | 256 | Hunyuan mesh detail, lower = less VRAM |
| `S2S_IM_DIR` | none | folder of your InstantMesh clone, turns on local InstantMesh |
| `S2S_IM_PYTHON` | backend python | `python.exe` of the InstantMesh env |
| `S2S_IM_CONFIG` | `configs/instant-mesh-large.yaml` | `configs/instant-mesh-base.yaml` is lighter on VRAM |
| `S2S_FAST` | `auto` | LCM-LoRA sampler (6 steps). On when no GPU |
| `S2S_STEPS` | 20 (6 fast) | diffusion steps for the render |
| `S2S_MVS_STEPS` | 50 | InstantMesh multi-view steps (30-75), API and local |
| `S2S_LOW_VRAM` | off | CPU offload for small GPUs |
| `S2S_REMBG_MODEL` | `u2net` | `u2netp` is smaller and faster |

## 3D backends

The last step (cutout -> mesh) has three backends. They are tried in order and
the next one is used when one fails:

| Name | What | Needs |
|---|---|---|
| `hunyuan` | Hunyuan3D-2mini on your GPU, shape only | `S2S_HY_PYTHON` (its own env) |
| `instantmesh_local` | InstantMesh on your GPU | `S2S_IM_DIR`, `S2S_IM_PYTHON` (its own env) |
| `instantmesh_api` | InstantMesh on the Hugging Face Space | internet, `HF_TOKEN` recommended |

Default order: `hunyuan,instantmesh_local,instantmesh_api`. A backend that is
not set up (for example no `S2S_IM_DIR`) is skipped, so with only Hunyuan
installed you get Hunyuan first and the API as the fallback. Change the order
with `S2S_MESH`. A single name turns the fallback off:

```
set S2S_MESH=hunyuan                       # Hunyuan only
set S2S_MESH=instantmesh_api,hunyuan       # API first, Hunyuan as fallback
```

(`instantmesh` still works as an alias of `instantmesh_api`.) The backend
prints the active order at start, and a finished job reports which backend made
it in the `backend` field of `/api/jobs/<id>`.

### Local InstantMesh setup

InstantMesh pins its own torch / diffusers versions and builds nvdiffrast, so it
needs a separate environment, not the backend one.

1. Clone https://github.com/TencentARC/InstantMesh and follow its install steps
   in a new env (Python 3.10, CUDA 12.1 torch, xformers,
   `pip install -r requirements.txt`). nvdiffrast is built from source, which on
   Windows needs the CUDA toolkit and the Visual Studio build tools.
2. Check it on its own first (the first run downloads the models):
   `python run.py configs/instant-mesh-large.yaml examples/hatsune_miku.png`
3. Point the backend at it, then start `python app.py`:

```
set S2S_IM_DIR=C:\path\to\InstantMesh
set S2S_IM_PYTHON=C:\path\to\instantmesh-env\python.exe
```

It needs an NVIDIA GPU. If it runs out of memory, use
`set S2S_IM_CONFIG=configs/instant-mesh-base.yaml`.

## API

- `POST /api/generate` (multipart `image`, optional `prompt`) -> `{job_id}`
- `GET /api/jobs/<job_id>` -> `status`, `label`, `step`, `model_url`, `backend`
- `GET /api/files/<job_id>/model.glb`
- `GET /api/health`

Tips: draw one object, dark lines, white background, no scribbled shading.