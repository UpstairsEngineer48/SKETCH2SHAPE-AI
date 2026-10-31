import argparse
from pathlib import Path

from huggingface_hub import hf_hub_download

REPO_ID = "creador/hunyuan3d-2mini-turbo-onnx"
MODEL_DIR = Path(__file__).resolve().parent / "models" / "hunyuan3d-2mini-turbo-onnx"
CONDITIONER_FILE = "dinov2_giant_1022_int8.onnx"
ALL_FILES = [
    CONDITIONER_FILE,
    "dit_turbo.onnx",
    "vae_kv.onnx",
    "vae_query.onnx",
]


def main():
    parser = argparse.ArgumentParser(description="Download Hunyuan3D-2mini-Turbo ONNX graphs")
    parser.add_argument(
        "--all", action="store_true",
        help="download all four graphs (the complete set is much larger); default downloads DINOv2 only",
    )
    args = parser.parse_args()
    files = ALL_FILES if args.all else [CONDITIONER_FILE]
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Repository: {REPO_ID}")
    print("Downloading: " + ", ".join(files))
    for filename in files:
        path = hf_hub_download(
            repo_id=REPO_ID,
            filename=filename,
            repo_type="model",
            local_dir=str(MODEL_DIR),
        )
        size_gib = Path(path).stat().st_size / (1024 ** 3)
        print(f"Ready: {filename} ({size_gib:.2f} GiB)")


if __name__ == "__main__":
    main()
