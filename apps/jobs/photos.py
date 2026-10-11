"""Handling an uploaded job or estimate photo (Phase 18 unit 2).

Every upload is decoded and re-encoded here, so what gets stored is
always a JPEG this code produced and never the bytes the phone sent.
That is not tidiness, it is the point:

**It strips the location.** A phone photo of a customer's house carries
GPS coordinates in its EXIF data — their home address, in a file that
staff can open. ADR 0009 promised that stripping and nothing had
implemented it. Re-encoding without passing `exif=` through drops the
lot: coordinates, timestamps, device and serial number.

It also keeps the files small. A modern phone photo is 3–12 MB and
several thousand pixels wide; a Raspberry Pi serving these off an SD
card does not want the originals, and nobody needs more than 2000px to
see whether the gutters are clean.

Orientation is applied before the metadata goes, or portrait photos
would all come out sideways — the rotation lives in the EXIF that is
about to be discarded.

On HEIC, which is what an iPhone shoots by default: Pillow here has no
HEIF support, so these cannot be decoded. iOS normally converts to
JPEG when handing a photo to a web upload, so this is rare in practice
— and when it does happen the person gets a sentence telling them what
happened rather than "Upload a valid image". See the phase log for why
`pillow-heif` was not added.
"""

from io import BytesIO

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from PIL import Image, ImageOps, UnidentifiedImageError

# A phone photo is a few megabytes; this leaves room for a big one
# without accepting a video somebody renamed.
MAX_UPLOAD_BYTES = 15 * 1024 * 1024
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
# Refuse an "image bomb": a small file that decodes to a huge bitmap.
MAX_PIXELS = 50_000_000
# Long edge. Enough to zoom into the work, small enough for an SD card
# and a phone on a bad signal.
MAX_EDGE = 2000
JPEG_QUALITY = 82

# What an iPhone shoots by default, and what Pillow here cannot read.
HEIF_FORMATS = {"HEIF", "HEIC", "AVIF"}
HEIF_SUFFIXES = (".heic", ".heif", ".avif")


def _looks_like_heif(uploaded):
    """Did they hand us a HEIC?

    Checked by name as well as by format, because Pillow cannot open
    one at all — it raises "cannot identify image file" like any other
    unreadable thing, and "that isn't an image" is a poor answer when
    it plainly is a photograph.
    """
    name = (getattr(uploaded, "name", "") or "").lower()
    return name.endswith(HEIF_SUFFIXES)


def process_photo(uploaded):
    """Validate an upload and return the JPEG to store.

    Raises `ValidationError` with a sentence worth reading. Returns a
    `ContentFile` named `photo.jpg`, so the stored name always ends
    `.jpg` and the serving view's content type is always right.
    """
    if uploaded.size > MAX_UPLOAD_BYTES:
        megabytes = MAX_UPLOAD_BYTES // (1024 * 1024)
        raise ValidationError(f"That photo is over {megabytes} MB. Take it again or pick another.")

    heif_by_name = _looks_like_heif(uploaded)
    try:
        with Image.open(uploaded) as probe:
            image_format = probe.format
            width, height = probe.size
            probe.verify()
    except (UnidentifiedImageError, OSError, SyntaxError):
        if heif_by_name:
            raise ValidationError(
                "That's a HEIC photo, which this app can't read yet. On an iPhone, "
                "Settings → Camera → Formats → Most Compatible saves photos as JPEG."
            ) from None
        raise ValidationError("That file isn't a photo we can read.") from None

    if image_format in HEIF_FORMATS or heif_by_name:
        raise ValidationError(
            "That's a HEIC photo, which this app can't read yet. On an iPhone, "
            "Settings → Camera → Formats → Most Compatible saves photos as JPEG."
        )
    if image_format not in ALLOWED_FORMATS:
        raise ValidationError("Use a JPEG, PNG or WebP photo.")
    if width * height > MAX_PIXELS:
        raise ValidationError("That photo is too large (over 50 megapixels).")

    uploaded.seek(0)
    with Image.open(uploaded) as source:
        # Rotate first: which way up it goes is recorded in the EXIF
        # that is about to be thrown away.
        image = ImageOps.exif_transpose(source)
        # JPEG has no alpha channel, and a PNG with transparency would
        # otherwise raise rather than flatten.
        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
        image.thumbnail((MAX_EDGE, MAX_EDGE), Image.Resampling.LANCZOS)
        out = BytesIO()
        # No `exif=` argument, so none of the original metadata — the
        # GPS coordinates above all — is carried into what is saved.
        image.save(out, format="JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)
    return ContentFile(out.getvalue(), name="photo.jpg")
