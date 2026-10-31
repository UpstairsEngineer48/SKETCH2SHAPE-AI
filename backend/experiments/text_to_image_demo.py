"""Legacy standalone text-to-image smoke test; not part of the Sketch2Shape pipeline."""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a standalone Stable Diffusion text-to-image test.")
    parser.add_argument(
        "--prompt",
        default="a photo of an astronaut riding a horse on mars",
        help="Text prompt for the demo image.",
    )
    parser.add_argument("--output", default="astronaut_rides_horse.png")
    parser.add_argument(
        "--model",
        default="stable-diffusion-v1-5/stable-diffusion-v1-5",
        help="Hugging Face Stable Diffusion model ID.",
    )
    args = parser.parse_args()

    try:
        import torch
        from diffusers import StableDiffusionPipeline
    except ImportError as exc:
        raise SystemExit("Install requirements-controlnet.txt to run this experiment.") from exc

    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.float16 if device == "cuda" else torch.float32
    pipeline = StableDiffusionPipeline.from_pretrained(args.model, torch_dtype=dtype)
    pipeline = pipeline.to(device)
    result = pipeline(args.prompt).images[0]

    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    result.save(output)
    print(f"Saved demo image to {output}")


if __name__ == "__main__":
    main()
