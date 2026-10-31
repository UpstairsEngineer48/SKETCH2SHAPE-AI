import cv2, numpy as np, torch
from PIL import Image
from diffusers import StableDiffusionControlNetPipeline, ControlNetModel, UniPCMultistepScheduler


import torch

device = "cuda" if torch.cuda.is_available() else "cpu"
dtype = torch.float16 if device == "cuda" else torch.float32

controlnet = ControlNetModel.from_pretrained(
    "lllyasviel/sd-controlnet-canny", dtype=dtype
)
pipe = StableDiffusionControlNetPipeline.from_pretrained(
    "stable-diffusion-v1-5/stable-diffusion-v1-5",
    controlnet=controlnet,
    dtype=dtype,
)
pipe.scheduler = UniPCMultistepScheduler.from_config(pipe.scheduler.config)

if device == "cuda":
    pipe.enable_model_cpu_offload()
else:
    pipe.to("cpu")

# 1. Make the control image (Canny edges)
img = np.array(Image.open("images.jpg").convert("RGB"))
edges = cv2.Canny(img, 100, 200)
edges = np.stack([edges] * 3, axis=-1)
control_image = Image.fromarray(edges)

# 2. Load ControlNet + base model
controlnet = ControlNetModel.from_pretrained(
    "lllyasviel/sd-controlnet-canny", torch_dtype=torch.float16
)
pipe = StableDiffusionControlNetPipeline.from_pretrained(
    "stable-diffusion-v1-5/stable-diffusion-v1-5",
    controlnet=controlnet,
    torch_dtype=torch.float16,
)
pipe.scheduler = UniPCMultistepScheduler.from_config(pipe.scheduler.config)
pipe.enable_model_cpu_offload()  # saves VRAM

# 3. Generate
result = pipe(
    "a futuristic chair, highly detailed",
    image=control_image,
    num_inference_steps=30,
    controlnet_conditioning_scale=1.0,  # strength of control
    guidance_scale=7.5,
).images[0]
result.save("output.png")