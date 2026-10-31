import cv2
from pathlib import Path

image_path = Path(__file__).resolve().parent / "images.jpg"

img = cv2.imread(str(image_path))

if img is not None:
    image = cv2.resize(img, (512,512))

    gray = cv2.cvtColor(
                        image,
                        cv2.COLOR_BGR2GRAY
                        )

    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blur, 50, 150)

    cv2.imshow('window', edges)
    cv2.waitKey(0)
    cv2.destroyAllWindows()