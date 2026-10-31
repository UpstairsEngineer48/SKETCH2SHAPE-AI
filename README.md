# Sketch2Shape AI

React/Vite frontend connected to a local FastAPI backend for image preprocessing and CPU-based Hunyuan3D DINOv2 ONNX conditioning.

> **Current implementation boundary:** the web UI is connected to the backend and can submit either a canvas sketch or an uploaded image. The backend performs foreground isolation, normalization, Canny diagnostic generation, and DINOv2 conditioning. It does **not** yet run the DiT sampler, ShapeVAE, mesh extraction, or GLB export. The UI reports this explicitly; a 3D mesh is not fabricated.

## Requirements

- Windows 10/11, 64-bit
- Python 3.11 recommended
- Node.js 18 or newer and npm
- Internet access for the first-time model and `rembg` weight downloads
- CPU inference only; no CUDA, WSL, or Ubuntu required

## Run locally (Windows PowerShell)

Open **two PowerShell terminals** in the project root.

### Terminal 1 — backend

```powershell
cd .\backend
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python download_models.py
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

The default model-download command fetches only the DINOv2 conditioner graph required by the currently connected stage. It is still a large model file. The first photo-background-removal request also downloads the default `rembg` U2Net weights.

To download all four Hunyuan ONNX graphs for later development, run this from `backend` instead:

```powershell
python download_models.py --all
```

### Terminal 2 — frontend

```powershell
cd .\frontend
npm install
npm run dev
```

Open the URL shown by Vite; with the supplied configuration it is:

- Frontend: http://127.0.0.1:5173
- Backend API docs: http://127.0.0.1:8000/docs
- Backend health: http://127.0.0.1:8000/health

The frontend sends API requests through Vite's `/api` proxy to FastAPI on port `8000`. You do not need to start another server or configure CORS manually for this local setup.

If PowerShell blocks virtual-environment activation, run this once in that terminal before activation:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

## Frontend-to-backend contract

| Frontend action | FastAPI endpoint | Result |
|---|---|---|
| Check backend connection | `GET /health` | Backend status, CPU provider, DINOv2 graph availability |
| Draw or upload an image, then run conditioning | `POST /debug/conditioner` | Preprocessing + DINOv2 embedding metadata and artifact URLs |
| Display generated preprocessing files | `GET /outputs/...` | Model input, foreground RGBA, alpha mask, Canny edge diagnostic |

The request is multipart form data:

- `image`: canvas PNG or uploaded image
- `input_type`: `sketch`, `photo`, or `auto`
- `remove_background`: boolean
- `prompt`: optional text; accepted by the API but not used by the current DINOv2 image-only stage

Canvas drawings are sent as `sketch`. Uploaded images can be set to Auto detect, Sketch/line drawing, or Photo/object image. The Photo option explicitly uses CPU `rembg`; Sketch uses adaptive thresholding so thin line work is not treated as a photograph.

## Preprocessing behavior

1. Decode the upload and apply EXIF orientation.
2. Preserve existing transparency where supplied.
3. For sketches, isolate ink from the paper background using adaptive thresholding.
4. For photos, use `rembg` on ONNX Runtime CPU.
5. Crop around the foreground, preserve aspect ratio, resize to about 85% of a 1022 × 1022 canvas, and center on white.
6. Produce a Canny edge map for visual quality control.
7. Pass normalized **RGB**, not the Canny map, to the DINOv2 ONNX graph.

Successful requests return image artifacts in the UI and the DINOv2 embedding shape/dtype/inference time. The current output is not a mesh.

## Useful endpoints

- `GET /health`
- `GET /models/info`
- `POST /debug/conditioner`
- `GET /docs`

## Repository layout

```text
backend/
  app/
    main.py
    config.py
    image_preprocess.py
    ort_utils.py
  models/                 # ignored; downloaded ONNX files
  outputs/                # ignored; per-request preprocessing artifacts
  download_models.py
  requirements.txt
frontend/
  src/
  package.json
  vite.config.js
backend_legacy/            # original experimental backend retained for reference
```
