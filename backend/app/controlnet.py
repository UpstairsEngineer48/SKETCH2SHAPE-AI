"""Optional Canny-ControlNet sketch-to-product-image refinement stage.

It is intentionally lazy-loaded so the basic image-to-3D service does not
need to download Stable Diffusion weights unless CONTROLNET_ENABLED=1.
"""

from __future__ import annotations

import os
import threading

import cv2
import numpy as np
from PIL import Image

_PIPELINE = None
_PIPELINE_LOCK = threading.Lock()


def enhance_with_controlnet(image: Image.Image, prompt: str = "") -> Image.Image:
    """Generate a product-style image while conditioning on Canny edges.

    TripoSR itself is image-conditioned, not text-conditioned. This optional
    stage is what gives the UI's text prompt an actual role in generation.
    """
    global _PIPELINE

    try:
        import torch
        from diffusers import (
            ControlNetModel,
            StableDiffusionControlNetPipeline,
            UniPCMultistepScheduler,
        )
    except ImportError as exc:
        raise RuntimeError(
            "ControlNet refinement is enabled but Diffusers/Accelerate are not installed. "
            "Install the optional ControlNet dependencies or set CONTROLNET_ENABLED=0."
        ) from exc

    with _PIPELINE_LOCK:
        if _PIPELINE is None:
            device = "cuda" if torch.cuda.is_available() else "cpu"
            dtype = torch.float16 if device == "cuda" else torch.float32
            controlnet_id = os.getenv("CONTROLNET_MODEL_ID", "lllyasviel/sd-controlnet-canny")
            base_model_id = os.getenv(
                "SD_BASE_MODEL_ID", "stable-diffusion-v1-5/stable-diffusion-v1-5"
            )

            controlnet = ControlNetModel.from_pretrained(
                controlnet_id,
                torch_dtype=dtype,
            )
            pipeline = StableDiffusionControlNetPipeline.from_pretrained(
                base_model_id,
                controlnet=controlnet,
                torch_dtype=dtype,
                safety_checker=None,
                requires_safety_checker=False,
            )
            pipeline.scheduler = UniPCMultistepScheduler.from_config(
                pipeline.scheduler.config
            )
            if device == "cuda":
                # Reduces peak VRAM at the cost of additional transfer overhead.
                pipeline.enable_model_cpu_offload()
            else:
                pipeline.to("cpu")
            _PIPELINE = pipeline

        rgb = np.asarray(image.convert("RGB").resize((512, 512), Image.Resampling.LANCZOS))
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        edges = cv2.Canny(gray, 60, 160)
        control_image = Image.fromarray(np.repeat(edges[:, :, None], 3, axis=2))

        guidance_prompt = prompt.strip() or (
            "A clean, realistic studio product image of the exact object represented by the "
            "input drawing, centered, complete object visible, neutral studio background, "
            "high quality product photography"
        )
        negative_prompt = (
            "multiple objects, duplicate object, cropped object, text, watermark, "
            "extra parts, cluttered background, distorted geometry"
        )
        generator = torch.Generator(device="cpu").manual_seed(
            int(os.getenv("CONTROLNET_SEED", "42"))
        )

        with torch.inference_mode():
            generated = _PIPELINE(
                prompt=guidance_prompt,
                negative_prompt=negative_prompt,
                image=control_image,
                num_inference_steps=int(os.getenv("CONTROLNET_STEPS", "20")),
                guidance_scale=float(os.getenv("CONTROLNET_GUIDANCE", "7.0")),
                controlnet_conditioning_scale=float(
                    os.getenv("CONTROLNET_STRENGTH", "0.85")
                ),
                generator=generator,
                height=512,
                width=512,
            ).images[0]
        return generated.convert("RGB")
