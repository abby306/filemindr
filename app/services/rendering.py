"""Render document pages to images for the source pane / thumbnails.

PDF pages are rasterized on demand with PyMuPDF (fitz) and cached by file hash;
raster images are served as-is (single page); other types (e.g. docx) have no
page render. This is the read side of provenance — the frontend overlays a
citation's bbox on the returned page image.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.services import ocr, storage

DEFAULT_DPI = 144
MIN_DPI = 72
MAX_DPI = 300


class PageOutOfRange(Exception):
    """Requested page is < 1 or beyond the document's page count."""


class PageNotRenderable(Exception):
    """The document's type has no page image (e.g. docx)."""


@dataclass(frozen=True)
class RenderedPage:
    media_type: str
    data: bytes


def _cache_path(file_hash: str, page: int, dpi: int) -> Path:
    return storage.get_storage_root() / "page_cache" / file_hash / f"p{page}_{dpi}.png"


def clamp_dpi(dpi: int) -> int:
    return max(MIN_DPI, min(MAX_DPI, dpi))


def render_page(
    *,
    storage_path: str,
    mime_type: str | None,
    file_hash: str,
    page: int,
    dpi: int = DEFAULT_DPI,
) -> RenderedPage:
    """Return one page as an image. PDFs rasterize+cache; images pass through.

    Raises `PageOutOfRange` for a bad page and `PageNotRenderable` for a type
    with no page render.
    """
    if page < 1:
        raise PageOutOfRange(f"page {page} < 1")
    dpi = clamp_dpi(dpi)

    if mime_type in ocr.IMAGE_MIMES:
        if page != 1:
            raise PageOutOfRange("images have a single page")
        return RenderedPage(mime_type, Path(storage_path).read_bytes())

    if mime_type == ocr.PDF_MIME:
        cache = _cache_path(file_hash, page, dpi)
        if cache.exists():
            return RenderedPage("image/png", cache.read_bytes())

        import fitz  # heavy; import lazily so module import stays cheap

        doc = fitz.open(storage_path)
        try:
            if page > doc.page_count:
                raise PageOutOfRange(f"page {page} > {doc.page_count}")
            pixmap = doc.load_page(page - 1).get_pixmap(dpi=dpi)
            data = pixmap.tobytes("png")
        finally:
            doc.close()

        cache.parent.mkdir(parents=True, exist_ok=True)
        tmp = cache.with_suffix(".tmp")
        tmp.write_bytes(data)
        tmp.replace(cache)  # atomic
        return RenderedPage("image/png", data)

    raise PageNotRenderable(f"no page image for {mime_type}")


def page_dimensions(
    storage_path: str, mime_type: str | None, ocr_engine: str | None
) -> dict[int, tuple[float, float]]:
    """Per-page (width, height) in the bbox coordinate space, keyed by 1-based
    page. Only PDFs are supported (bbox is in PDF points for the text-layer path,
    or 200-DPI pixels for the Vision path); other types return {} so bboxes fall
    back to a page-level highlight.
    """
    if mime_type != ocr.PDF_MIME:
        return {}
    import fitz  # lazy

    scale = 200.0 / 72.0 if ocr_engine == "google_vision" else 1.0
    doc = fitz.open(storage_path)
    try:
        dims: dict[int, tuple[float, float]] = {}
        for i in range(doc.page_count):
            rect = doc.load_page(i).rect
            dims[i + 1] = (rect.width * scale, rect.height * scale)
        return dims
    finally:
        doc.close()


def normalize_bbox(
    polygon: list[list[float]] | None, page_w: float, page_h: float
) -> list[float] | None:
    """A 4-vertex polygon → normalized ``[x, y, w, h]`` in [0,1], or None."""
    if not polygon or page_w <= 0 or page_h <= 0:
        return None
    xs = [p[0] for p in polygon]
    ys = [p[1] for p in polygon]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    return [x0 / page_w, y0 / page_h, (x1 - x0) / page_w, (y1 - y0) / page_h]
