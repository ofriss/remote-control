from io import BytesIO

from PIL import Image, ImageGrab

from constants import JPEG_IMAGE_QUALITY

# TODO: Different monitors. IDEA: HELLO will send the monitors available. Then screenshot the respective one.

class ImageHandler:
    @staticmethod
    def screenshot() -> Image.Image:
        return ImageGrab.grab()

    @staticmethod
    def from_buffer(buffer: BytesIO) -> Image.Image:
        return Image.open(buffer)

    @staticmethod
    def to_buffer(image: Image.Image) -> BytesIO:
        buffer = BytesIO()

        # JPEG doesn't support RGBA, just for safety
        image.convert("RGB").save(
            buffer,
            format="JPEG",
            quality=JPEG_IMAGE_QUALITY,
            optimize=True
        )

        return buffer

    @staticmethod
    def to_bytes(image: Image.Image) -> bytes:
        return ImageHandler.to_buffer(image).getvalue()
