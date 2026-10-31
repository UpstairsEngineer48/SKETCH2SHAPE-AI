# Sketch2Shape AI

Sketch -> ControlNet render -> background removal -> InstantMesh -> GLB viewer.

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
| `S2S_FAST` | `auto` | LCM-LoRA sampler (6 steps). On when no GPU |
| `S2S_STEPS` | 20 (6 fast) | diffusion steps for the render |
| `S2S_MVS_STEPS` | 50 | InstantMesh multi-view steps (30-75) |
| `S2S_LOW_VRAM` | off | CPU offload for small GPUs |
| `S2S_REMBG_MODEL` | `u2net` | `u2netp` is smaller and faster |

## API

- `POST /api/generate` (multipart `image`, optional `prompt`) -> `{job_id}`
- `GET /api/jobs/<job_id>` -> `status`, `label`, `step`, `model_url`
- `GET /api/files/<job_id>/model.glb`
- `GET /api/health`

Tips: draw one object, dark lines, white background, no scribbled shading.
