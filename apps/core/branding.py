"""Logo upload handling (Phase 17.5 step 3).

Every upload is decoded and re-encoded here, so what's stored is always a
small square PNG with no metadata — never the uploaded bytes. The page's
crop tool only chooses the square (crop_x / crop_y / crop_size, in the
original image's pixels); without JavaScript the center square is used.
"""

from io import BytesIO

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
ALLOWED_FORMATS = {"JPEG", "PNG", "GIF", "WEBP"}
# Refuse "image bombs" — a small file that decodes to a huge bitmap.
MAX_PIXELS = 40_000_000
LOGO_SIZE = 512


def _crop_box(width, height, crop):
    side = min(width, height)
    default = ((width - side) // 2, (height - side) // 2, side)
    if not crop:
        return default
    x, y, size = crop
    if size < 16 or x < 0 or y < 0 or x + size > width or y + size > height:
        return default
    return x, y, size


def process_logo(uploaded, crop=None):
    """Validate an uploaded image and return a ContentFile holding the
    cropped, resized PNG. Raises ValidationError with a plain message."""
    if uploaded.size > MAX_UPLOAD_BYTES:
        raise ValidationError("That file is over 5 MB. Choose a smaller image.")
    try:
        with Image.open(uploaded) as probe:
            image_format = probe.format
            width, height = probe.size
            probe.verify()
    except (UnidentifiedImageError, OSError, SyntaxError):
        raise ValidationError("That file isn't an image we can read.") from None
    if image_format not in ALLOWED_FORMATS:
        raise ValidationError("Use a JPEG, PNG, GIF, or WebP image.")
    if width * height > MAX_PIXELS:
        raise ValidationError("That image is too large (over 40 megapixels).")

    uploaded.seek(0)
    with Image.open(uploaded) as source:
        source.seek(0)  # first frame of an animated GIF
        image = ImageOps.exif_transpose(source).convert("RGBA")
    x, y, size = _crop_box(image.width, image.height, crop)
    image = image.crop((x, y, x + size, y + size))
    image.thumbnail((LOGO_SIZE, LOGO_SIZE), Image.Resampling.LANCZOS)

    out = BytesIO()
    image.save(out, format="PNG", optimize=True)
    return ContentFile(out.getvalue(), name="logo.png")
