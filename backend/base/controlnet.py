"""
controlnet.py
Control image -> rendered object image using ControlNet (Canny) + SD 1.5.

Models are loaded lazily (see load()), so importing this file is instant and
Flask can start answering requests while the weights download/load.

Environment variables (all optional):
  S2S_FAST      auto|1|0   LCM-LoRA sampler (~6 steps). auto = on when no GPU.
  S2S_STEPS     int        override the number of diffusion steps
  S2S_LOW_VRAM  1          use CPU offload on small GPUs (slower, saves VRAM)
  S2S_SD_MODEL  repo id    base Stable Diffusion 1.5 checkpoint
"""

import logging
import os
import threading
from pathlib import Path

log=logging.getLogger(__name__)

SD_ID=os.getenv("S2S_SD_MODEL","stable-diffusion-v1-5/stable-diffusion-v1-5")
CONTROLNET_ID="lllyasviel/sd-controlnet-canny"
LCM_LORA_ID="latent-consistency/lcm-lora-sdv1-5"

# InstantMesh works best on ONE centred object on a plain background.
STYLE_SUFFIX=("single object, centered, whole object in frame, plain white background, "
              "soft studio lighting, product render, high detail")
NEGATIVE=("background, scenery, table, floor, shadow, text, watermark, multiple objects, "
          "cropped, out of frame, lowres, blurry, deformed")

_state={"pipe":None,"device":None,"fast":False,"loading":False,"error":None}
_lock=threading.Lock()


def status():
    """Small dict used by /api/health."""
    return {
        "loaded":_state["pipe"] is not None,
        "loading":_state["loading"],
        "device":_state["device"],
        "fast":_state["fast"],
        "error":_state["error"],
    }


def _want_fast(device):
    mode=os.getenv("S2S_FAST","auto").lower()
    if mode in("1","true","yes","on"):
        return True
    if mode in("0","false","no","off"):
        return False
    return device!="cuda"


def load():
    """Load the pipeline once (thread-safe). Returns the pipeline."""
    with _lock:
        if _state["pipe"] is not None:
            return _state["pipe"]
        _state["loading"]=True
        _state["error"]=None
        try:
            import torch
            from diffusers import (ControlNetModel,StableDiffusionControlNetPipeline,
                                   UniPCMultistepScheduler)

            device="cuda" if torch.cuda.is_available() else "cpu"
            dtype=torch.float16 if device=="cuda" else torch.float32
            log.info("Loading ControlNet + SD1.5 on %s (%s)...",device,dtype)
            if device=="cpu":
                log.warning("No CUDA GPU detected - generation will be slow. "
                            "If you have an NVIDIA GPU, install the CUDA build of torch "
                            "(see README).")

            controlnet=ControlNetModel.from_pretrained(CONTROLNET_ID,torch_dtype=dtype)
            pipe=StableDiffusionControlNetPipeline.from_pretrained(
                SD_ID,
                controlnet=controlnet,
                torch_dtype=dtype,
                safety_checker=None,           # false positives return black images
                requires_safety_checker=False,
            )
            base_scheduler_config=pipe.scheduler.config

            fast=_want_fast(device)
            if fast:
                try:
                    from diffusers import LCMScheduler
                    pipe.load_lora_weights(LCM_LORA_ID)
                    pipe.fuse_lora()
                    pipe.scheduler=LCMScheduler.from_config(base_scheduler_config)
                except Exception as exc:
                    log.warning("LCM fast mode unavailable (%s). Using the normal sampler.",exc)
                    fast=False
            if not fast:
                pipe.scheduler=UniPCMultistepScheduler.from_config(base_scheduler_config)

            if device=="cuda" and os.getenv("S2S_LOW_VRAM")=="1":
                pipe.enable_model_cpu_offload()
            else:
                pipe.to(device)

            _state.update(pipe=pipe,device=device,fast=fast)
            log.info("Model ready (device=%s, fast=%s).",device,fast)
            return pipe
        except Exception as exc:
            _state["error"]=f"{type(exc).__name__}: {exc}"
            log.exception("Model loading failed")
            raise
        finally:
            _state["loading"]=False


def sketch_to_image(control_path,prompt,output_path,seed=None,controlnet_scale=1.0):
    """
    Render an image from the control image produced by preprocessing.py.

    Args:
        control_path:      white-lines-on-black control image (already edges!).
        prompt:            what the object is.
        output_path:       where to save the rendered PNG.
        seed:              optional int for reproducible results.
        controlnet_scale:  how strictly the lines are followed (0-2).
    """
    import torch
    from PIL import Image

    pipe=load()
    fast=_state["fast"]
    steps=int(os.getenv("S2S_STEPS","0")) or(6 if fast else 20)
    guidance=1.5 if fast else 7.5

    control=Image.open(control_path).convert("RGB")
    generator=None
    if seed is not None:
        generator=torch.Generator(device="cpu").manual_seed(int(seed))

    log.info("Rendering: %d steps, guidance %.1f, fast=%s",steps,guidance,fast)
    result=pipe(
        f"{prompt}, {STYLE_SUFFIX}",
        negative_prompt=NEGATIVE,
        image=control,
        num_inference_steps=steps,
        guidance_scale=guidance,
        controlnet_conditioning_scale=controlnet_scale,
        generator=generator,
    ).images[0]

    result.save(output_path)
    return Path(output_path)
