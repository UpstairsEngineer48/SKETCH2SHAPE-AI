from rembg import remove
from PIL import Image

def remove_background(input_path, output_path):
    image = Image.open(input_path)
    output = remove(image)
    output.save(output_path)
    return output_path

remove_background(
    "outputs/foreground.png",
    "outputs/generated.png"
)