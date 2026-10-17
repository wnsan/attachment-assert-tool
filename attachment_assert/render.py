"""Turn any supported file into a list of RGB page images."""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageSequence

DEFAULT_DPI = 150

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff", ".webp"}
PDF_EXTS = {".pdf"}
OFFICE_EXTS = {
    ".doc", ".docx", ".odt", ".rtf", ".xls", ".xlsx", ".ods", ".csv",
    ".ppt", ".pptx", ".odp", ".txt", ".html", ".htm",
}


class RenderError(RuntimeError):
    pass


def supported_exts() -> list[str]:
    exts = set(IMAGE_EXTS) | PDF_EXTS
    if find_soffice():
        exts |= OFFICE_EXTS
    return sorted(exts)


def find_soffice() -> str | None:
    for name in ("soffice", "libreoffice"):
        path = shutil.which(name)
        if path:
            return path
    for candidate in (
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
        "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    ):
        if os.path.exists(candidate):
            return candidate
    return None


def _sniff_kind(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in PDF_EXTS:
        return "pdf"
    if ext in IMAGE_EXTS:
        return "image"
    if ext in OFFICE_EXTS:
        return "office"
    with open(path, "rb") as fh:
        head = fh.read(8)
    if head.startswith(b"%PDF"):
        return "pdf"
    try:
        with Image.open(path):
            return "image"
    except Exception:
        pass
    raise RenderError(f"Unsupported file type: {path.name}")


def render_pdf(path: Path, dpi: int = DEFAULT_DPI) -> list[Image.Image]:
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(str(path))
    try:
        scale = dpi / 72.0
        pages = []
        for i in range(len(pdf)):
            page = pdf[i]
            bitmap = page.render(scale=scale)
            pages.append(bitmap.to_pil().convert("RGB"))
            page.close()
        return pages
    finally:
        pdf.close()


def render_image(path: Path) -> list[Image.Image]:
    with Image.open(path) as img:
        frames = []
        for frame in ImageSequence.Iterator(img):
            frame = frame.convert("RGBA")
            bg = Image.new("RGBA", frame.size, (255, 255, 255, 255))
            frames.append(Image.alpha_composite(bg, frame).convert("RGB"))
        return frames


def convert_office_to_pdf(path: Path) -> Path:
    soffice = find_soffice()
    if not soffice:
        raise RenderError(
            f"{path.suffix} files need LibreOffice (soffice) on PATH to convert to PDF"
        )
    outdir = Path(tempfile.mkdtemp(prefix="attachment_assert_"))
    subprocess.run(
        [soffice, "--headless", "--convert-to", "pdf", "--outdir", str(outdir), str(path)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=180,
    )
    out = outdir / (path.stem + ".pdf")
    if not out.exists():
        raise RenderError(f"LibreOffice failed to convert {path.name}")
    return out


def render_file(path: str | os.PathLike, dpi: int = DEFAULT_DPI) -> list[Image.Image]:
    """Render every page/frame of *path* to an RGB image.

    PDFs and office documents are rasterised at *dpi*; images keep their native pixels.
    """
    path = Path(path)
    if not path.exists():
        raise RenderError(f"File not found: {path}")
    kind = _sniff_kind(path)
    if kind == "pdf":
        return render_pdf(path, dpi)
    if kind == "image":
        return render_image(path)
    return render_pdf(convert_office_to_pdf(path), dpi)
