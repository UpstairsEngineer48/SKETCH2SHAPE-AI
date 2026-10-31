# Sketch2Shape AI

A sketch/image-to-3D prototype for the TechZephyr 4.0 challenge. The current backend uses the pretrained **TripoSR** single-image reconstruction model and exports a validated `.glb` or `.obj` mesh. The React + Three.js frontend supports drawing, image upload, an optional text field, interactive orbit inspection, and download.

## Current implementation status

| Stage | Status | Implementation |
|---|---|---|
| Draw sketch | Implemented | `frontend/src/components/SketchCanvas.jsx` |
| Upload image | Implemented | `frontend/src/components/UploadPanel.jsx` |
| Frontend API client | Implemented | `frontend/src/lib/api.js` |
| Input conditioning | Implemented | `backend/app/preprocessing.py` |
| Optional sketch-guided image refinement | Optional; off by default | `backend/app/controlnet.py` |
| Image-to-3D | Integrated; pretrained weights downloaded on first inference | `backend/app/triposr.py` |
| Mesh validation and GLB/OBJ export | Implemented | `backend/app/export.py` |
| API endpoints | Implemented | `backend/app/main.py` |
| Browser 3D preview | Implemented | `frontend/src/components/ModelViewer.jsx` |

**Important:** The archive also contained a hardcoded Stable Diffusion text-to-image experiment (astronaut prompt); it has been moved to `backend/experiments/text_to_image_demo.py` and made import-safe. It is not connected to the sketch pipeline. The archive contained an experimental background-removal script and a ControlNet script, but no backend API and no image-to-3D implementation. The sample `foreground.png` / `generated.png` files are a dog photo and its background-removed result; neither file is a 3D output. The new backend replaces those hardcoded experiments with request-driven functions.

## Pipeline

```text
Draw / upload image + optional prompt
                 |
                 v
      FastAPI POST /generate
                 |
                 v
  Image validation and conditioning
  - draw canvas: estimate transparency from white paper
  - transparent upload: retain alpha
  - detect white-paper line drawings and estimate a background mask
  - optionally remove photo backgrounds with rembg (`REMOVE_BACKGROUND_UPLOADS=1`)
  - normalize/crop/pad to centered 512 x 512 RGB
                 |
                 v
  [Optional] Canny ControlNet image refinement
  - only when CONTROLNET_ENABLED=1
  - uses the supplied prompt and sketch edges
                 |
                 v
       Pretrained TripoSR
  - single-image feed-forward reconstruction
  - extract mesh with vertex colors
                 |
                 v
      Mesh validation (trimesh)
                 |
                 v
          model.glb / model.obj
                 |
                 v
  /assets/{job_id}/model.{format} -> Three.js viewer + download
```

TripoSR is image-conditioned, not text-conditioned. Therefore, with the default `CONTROLNET_ENABLED=0`, the prompt is accepted by the API but **does not alter the reconstruction**. Enable the optional ControlNet stage to make the prompt influence the generated image before TripoSR. This stage requires additional Diffusers dependencies and downloads additional model weights.

## Hardware and runtime notes

- Use **Python 3.10** in a dedicated environment. TripoSR has an upstream native extension dependency (`torchmcubes`), so installation is more predictable in Ubuntu or WSL2 Ubuntu than in native Windows.
- Install a PyTorch build matching the installed NVIDIA driver/CUDA runtime. Do not blindly copy a CUDA wheel command from another machine; select the appropriate build from the [PyTorch installation selector](https://pytorch.org/get-started/locally/).
- The upstream TripoSR README documents approximately **6 GB VRAM** for its default single-image inference settings. CPU fallback is implemented, but it is much slower and can consume substantial system RAM.
- First inference downloads the pretrained weights from Hugging Face. It therefore needs network access and disk space. Subsequent requests reuse the model loaded in the backend process.
- The default mesh extraction resolution is 256. Increasing it may increase memory use and inference time.
- The output contains real mesh vertices and faces. The default GLB preserves vertex-color appearance; it is not a flat textured image.
- A single view cannot reveal the true hidden surfaces. The model predicts a plausible completion; it does not recover ground-truth geometry.
- We have not run neural inference in the code-generation environment because it has CPU-only PyTorch and no CUDA GPU. The API, preprocessing and export can be tested independently; the frontend production build and final neural inference must still be verified in the target development environment.

## Backend setup (recommended: Ubuntu / WSL2)

1. Create and activate a Python 3.10 environment.
2. Install PyTorch for the target CUDA setup, following the official PyTorch selector.
3. From the repository root, run:

   ```bash
   bash backend/setup_triposr.sh
   ```

   This clones the official TripoSR repository into `backend/vendor/TripoSR` and installs this project's API requirements plus the upstream TripoSR requirements. It does not choose or install PyTorch for you.

4. Start the API:

   ```bash
   cd backend
   python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
   ```

5. Check `http://127.0.0.1:8000/health` and `http://127.0.0.1:8000/docs`.

The first `/generate` request loads the model and downloads its weights if they are not cached yet. Keep the backend process running to reuse the loaded model between generations.

### Optional ControlNet refinement

Install the optional dependencies in the same environment:

```bash
pip install "diffusers>=0.27" "accelerate>=0.27" "safetensors>=0.4"
```

Copy `backend/.env.example` to `backend/.env` or set the environment variables in your shell, then set:

```text
CONTROLNET_ENABLED=1
```

The optional stage uses Canny ControlNet + Stable Diffusion 1.5. Its first run downloads additional weights and is considerably slower and more memory-intensive than direct TripoSR reconstruction. Install its packages with `pip install -r requirements-controlnet.txt`. Start with the default direct path; enable it only after verifying TripoSR by itself.

## Frontend setup

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. The Vite development proxy forwards `/api/*` to `http://127.0.0.1:8000/*`.

For a non-local backend, create `frontend/.env` and set `VITE_API_BASE_URL` to the backend base URL (for example, `https://your-api.example.com`).

## API contract

### `GET /health`

Returns API status, whether TripoSR has loaded, selected device, and whether ControlNet refinement is enabled.

### `POST /generate`

Multipart form fields:

- `image`: PNG, JPEG or WEBP input image
- `input_type`: `draw` or `upload`
- `prompt`: optional text, maximum 400 characters
- `file_format`: optional `glb` (default) or `obj`

Example response:

```json
{
  "job_id": "a1b2c3d4e5f6",
  "model_url": "/assets/a1b2c3d4e5f6/model.glb",
  "format": "glb",
  "filename": "sketch2shape-a1b2c3d4e5f6.glb",
  "prompt_used": false,
  "note": "Single-image TripoSR reconstruction.",
  "mesh": {
    "vertices": 32000,
    "faces": 64000,
    "is_watertight": false,
    "device": "cuda:0"
  }
}
```

The numerical mesh values above are illustrative only; actual values depend on the input and model inference. `model_url` is returned as a relative path so the Vite `/api` proxy can serve it during local development.

## Testing

Install the lightweight project test dependencies and run the backend tests:

```bash
pip install -r requirements-dev.txt
PYTHONPATH=backend pytest -q backend/tests
```

The API contract test substitutes a small synthetic mesh for the neural model. It verifies upload handling, preprocessing, GLB serialization, and asset serving without pretending that TripoSR inference ran. A real model test requires the upstream checkout, downloaded weights, and suitable GPU/CPU resources.

## Configuration

The API loads `backend/.env` when present and also accepts environment variables from the shell. Copy `backend/.env.example` to `backend/.env` to configure it. The most useful initial settings are:

- `TRIPOSR_REPO`: path to a TripoSR checkout if it is not in `backend/vendor/TripoSR`
- `TRIPOSR_CHUNK_SIZE`: lower values reduce VRAM usage at the cost of speed
- `MESH_RESOLUTION`: marching-cubes mesh extraction resolution
- `OUTPUT_FORMAT`: default `glb`
- `MAX_UPLOAD_MB`: upload size limit
- `REMOVE_BACKGROUND_UPLOADS=1`: run rembg on uploaded photographs (enabled by default after installing TripoSR requirements; detected white-paper sketches bypass rembg)
- `CONTROLNET_ENABLED`: optional prompt-guided refinement toggle

## Known limitations / next engineering steps

1. Validate sketch-to-mesh quality with diverse hand-drawn objects; TripoSR was designed for single images and a line drawing may be a harder input than a product photograph.
2. Compare the direct TripoSR output with the optional ControlNet-refined image output.
3. Test the optional rembg foreground removal on photographs with cluttered backgrounds and tune it for the target image set.
4. Record real generation time, GPU memory use and output quality on the target hardware before documenting benchmark claims.
5. Add a queue / job status endpoint if multiple users will generate simultaneously. The current backend serializes GPU inference within the process.

## Third-party model attribution

- [TripoSR](https://github.com/VAST-AI-Research/TripoSR), VAST-AI Research / Stability AI. The upstream project states that code and pretrained models are released under the MIT license; retain the upstream license and notices when distributing it.
- Optional: [Diffusers ControlNet](https://huggingface.co/lllyasviel/sd-controlnet-canny) and the Stable Diffusion 1.5 base model. Check and disclose each model's applicable model-card license and usage restrictions before public or commercial deployment.
