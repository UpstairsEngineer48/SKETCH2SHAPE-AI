# Sketch2Shape AI

Sketch -> ControlNet render -> background removal -> 3D mesh (Hunyuan3D or InstantMesh) -> GLB viewer.

## Run it

**Backend** (terminal 1)

```
cd ./backend
.venv\Scripts\activate
$env:HF_TOKEN="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"  #example hugging face token
$env:S2S_HY_PYTHON="C:\Users\PRANJAL\Hunyuan3D-2\.venv\Scripts\python.exe"
$env:S2S_IM_DIR="C:\Users\PRANJAL\InstantMesh"
$env:S2S_IM_PYTHON="C:\Users\PRANJAL\InstantMesh\.venv\Scripts\python.exe"
$env:S2S_IM_CONFIG="configs/lowvram/instant-mesh-base.yaml"
$env:S2S_LOW_VRAM="1"
$env:PYTORCH_CUDA_ALLOC_CONF="max_split_size_mb:128"
$env:S2S_MESH="hunyuan,instantmesh_local,instantmesh_api"

# NVIDIA GPU? install the CUDA torch FIRST (pick your CUDA version on pytorch.org):
pip install torch --index-url https://download.pytorch.org/whl/cu121
pip install -r ../requirements.txt
python app.py
```

**Frontend** (terminal 2)

```
cd ./frontend
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

### 3D backends

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


### Hunyuan3D setup (shape-only engine)

Hunyuan3D runs in its own environment, started by the backend as a separate process.

1. Clone the repo and make an env (PowerShell):

   git clone https://github.com/Tencent/Hunyuan3D-2.git
   cd Hunyuan3D-2
   python -m venv .venv
   .venv\Scripts\activate

2. Install CUDA torch first, then the repo:

   pip install torch --index-url https://download.pytorch.org/whl/cu121
   pip install -r requirements.txt
   pip install -e .

   Only the shape model is used, so the texture extensions (custom_rasterizer,
   differentiable_renderer) do NOT need to be built.

3. Check the install:

   python -c "from hy3dgen.shapegen import Hunyuan3DDiTFlowMatchingPipeline; print('ok')"

4. Point the backend at it before `python app.py`:

   $env:S2S_HY_PYTHON="C:\path\to\Hunyuan3D-2\.venv\Scripts\python.exe"

The model weights (tencent/Hunyuan3D-2mini) download automatically on the first
job, so that run is slower. If it runs out of memory, lower `S2S_HY_OCT` (e.g. 192).

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
