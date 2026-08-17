from io import BytesIO
from unittest.mock import patch

from PIL import Image

from image import ImageHandler

JPEG_MAGIC = b"\xff\xd8"


def make_image(mode="RGB", size=(10, 10), color=(255, 0, 0)) -> Image.Image:
    return Image.new(mode, size, color)


# --- screenshot ---

def test_screenshot_delegates_to_image_grab():
    expected = make_image()
    with patch("image.ImageGrab.grab", return_value=expected) as grab:
        result = ImageHandler.screenshot()

    grab.assert_called_once_with()
    assert result is expected


# --- to_buffer ---

def test_to_buffer_produces_jpeg_bytes():
    buffer = ImageHandler.to_buffer(make_image())
    assert isinstance(buffer, BytesIO)
    assert buffer.getvalue().startswith(JPEG_MAGIC)


def test_to_buffer_converts_rgba_to_rgb():
    image = make_image(mode="RGBA", color=(255, 0, 0, 128))
    buffer = ImageHandler.to_buffer(image)

    reopened = Image.open(buffer)
    assert reopened.mode == "RGB"


def test_to_buffer_preserves_dimensions():
    image = make_image(size=(37, 21))
    reopened = Image.open(ImageHandler.to_buffer(image))
    assert reopened.size == (37, 21)


# --- to_bytes ---

def test_to_bytes_matches_to_buffer_contents():
    image = make_image()
    assert ImageHandler.to_bytes(image) == ImageHandler.to_buffer(image).getvalue()


def test_to_bytes_returns_jpeg_bytes():
    assert ImageHandler.to_bytes(make_image()).startswith(JPEG_MAGIC)


# --- from_buffer ---

def test_from_buffer_roundtrips_to_buffer_output():
    original = make_image(size=(16, 16))
    buffer = ImageHandler.to_buffer(original)

    reopened = ImageHandler.from_buffer(buffer)

    assert reopened.size == original.size
    assert reopened.format == "JPEG"
