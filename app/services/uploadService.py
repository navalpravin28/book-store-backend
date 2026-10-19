import asyncio
import io
import uuid

from fastapi import UploadFile
from PIL import Image, ImageOps

from app.core.config import settings
from app.core.exception import BadRequestException, PayloadTooLargeException
from app.core.utils import LOCAL_IMAGE_RE

Image.MAX_IMAGE_PIXELS = 25_000_000  # decompression-bomb guard
MAX_DIMENSION = 6000

# sniffed type -> (PIL format, extension, content type)
_TYPES = {
    "jpeg": ("JPEG", "jpg", "image/jpeg"),
    "png": ("PNG", "png", "image/png"),
    "webp": ("WEBP", "webp", "image/webp"),
    "avif": ("AVIF", "avif", "image/avif"),
}


def _sniff(data: bytes) -> str | None:
    if data[:3] == b"\xff\xd8\xff":
        return "jpeg"

    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"

    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"

    # AVIF uses the ISO Base Media File Format (ISOBMFF)
    if len(data) >= 12 and data[4:8] == b"ftyp":
        brand = data[8:12]

        if brand in (b"avif", b"avis"):
            return "avif"

        # Check compatible brands in the file's ftyp box
        box_size = int.from_bytes(data[:4], "big")
        ftyp_end = min(box_size, len(data))

        if box_size >= 16:
            compatible_brands = data[16:ftyp_end]

            if (
                b"avif" in compatible_brands
                or b"avis" in compatible_brands
            ):
                return "avif"

    return None

def _process_image(data: bytes, kind_key: str) -> bytes:
    """Decode and re-encode the image to strip EXIF/GPS and embedded payloads."""
    pil_format = _TYPES[kind_key][0]

    try:
        with Image.open(io.BytesIO(data)) as probe:
            if probe.format != pil_format:
                raise BadRequestException(
                    "File content does not match an allowed image type"
                )
            probe.verify()

        with Image.open(io.BytesIO(data)) as img:
            img.load()

            if max(img.size) > MAX_DIMENSION:
                raise BadRequestException(
                    f"Image too large (max {MAX_DIMENSION}px per side)"
                )

            img = ImageOps.exif_transpose(img)
            out = io.BytesIO()

            if pil_format == "JPEG":
                if img.mode not in ("RGB", "L"):
                    img = img.convert("RGB")
                img.save(out, format="JPEG", quality=88, optimize=True)

            elif pil_format == "PNG":
                img.save(out, format="PNG", optimize=True)

            elif pil_format == "WEBP":
                img.save(out, format="WEBP", quality=88)

            elif pil_format == "AVIF":
                img.save(out, format="AVIF", quality=88)

            return out.getvalue()

    except BadRequestException:
        raise
    except Exception as exc:
        raise BadRequestException(
            "Invalid or unsupported image file"
        ) from exc

class UploadService:
    @staticmethod
    async def read_limited(file: UploadFile, max_bytes: int) -> bytes:
        """Reads in chunks and aborts as soon as the limit is crossed (no unbounded memory use)."""
        chunks, total = [], 0
        while chunk := await file.read(64 * 1024):
            total += len(chunk)
            if total > max_bytes:
                raise PayloadTooLargeException(f"File too large (max {max_bytes // (1024 * 1024)} MB)")
            chunks.append(chunk)
        return b"".join(chunks)

    async def save_image(self, file: UploadFile, kind: str) -> dict:
        data = await self.read_limited(file, settings.MAX_IMAGE_SIZE_MB * 1024 * 1024)
        if not data:
            raise BadRequestException("Empty file")

        sniffed = _sniff(data)  # we trust the bytes, never the filename or Content-Type header
        if sniffed is None:
            raise BadRequestException("Only JPEG, PNG or WEBP images are allowed")

        try:
            clean = await asyncio.to_thread(_process_image, data, sniffed)
        except BadRequestException:
            raise
        except Exception:
            raise BadRequestException("Invalid or corrupted image")

        _, ext, content_type = _TYPES[sniffed]
        name = f"{uuid.uuid4().hex}.{ext}"  # server-generated name: no traversal, no overwrite
        directory = settings.UPLOAD_ROOT / kind
        await asyncio.to_thread(directory.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread((directory / name).write_bytes, clean)
        return {"imageUrl": f"/static/uploads/{kind}/{name}", "contentType": content_type, "size": len(clean)}

    @staticmethod
    def delete_local(image_url: str | None) -> None:
        """Deletes a previously uploaded file. Ignores external URLs and anything outside the upload dir."""
        if not image_url or not LOCAL_IMAGE_RE.match(image_url):
            return
        root = settings.UPLOAD_ROOT.resolve()
        path = (settings.STATIC_ROOT / image_url.removeprefix("/static/")).resolve()
        if path.is_relative_to(root):
            path.unlink(missing_ok=True)
