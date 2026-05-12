"""Generate an inline-PDF HTML wrapper so a beat can open a PDF page in
headless Chromium without triggering a download (GOTCHAS #4).

Rasterizes the requested page via pymupdf and renders the
`recipes/inline_pdf.html.j2` template around it.

CLI:
    uv run helpers/pdf_wrapper.py \\
      --working-dir <path> \\
      --pdf-id spme_2024_09_p60 \\
      --pdf-source <local-path-or-http-url> \\
      --page 60 \\
      [--citation "SPME §6.2.2"]

Outputs into <working_dir>/_assets/:
    pdfs/<pdf-id>.pdf
    pdf_pages/<pdf-id>_p<N>.png
    pdf_wrappers/<pdf-id>_p<N>.html

The wrapper HTML can be opened via `file:///<absolute-path>` from Playwright.
"""
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml", "pymupdf", "jinja2"]
# ///
import argparse
import sys
import urllib.error
import urllib.request
from pathlib import Path

import fitz  # pymupdf
from jinja2 import Environment, FileSystemLoader, select_autoescape

# scripts/_lib.py also lives one level up
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from _lib import resolve_working_dir, ensure_dir


SKILL_ROOT = Path(__file__).parent.parent
RECIPES_DIR = SKILL_ROOT / "recipes"


def fetch_pdf(source: str, dest: Path) -> None:
    if source.startswith(("http://", "https://")):
        if dest.exists():
            return
        print(f"  fetching {source}")
        # Timed urlopen + atomic rename: no half-written files left behind on
        # failure (a partial dest would fool the .exists() check above next run).
        tmp = dest.with_suffix(dest.suffix + ".part")
        try:
            with urllib.request.urlopen(source, timeout=30) as r:
                tmp.write_bytes(r.read())
            tmp.rename(dest)
        except (urllib.error.URLError, TimeoutError) as e:
            tmp.unlink(missing_ok=True)
            sys.exit(f"Failed to fetch PDF {source!r}: {e}")
    else:
        src = Path(source).expanduser().resolve()
        if not src.exists():
            sys.exit(f"PDF source not found: {src}")
        if dest.exists() and dest.samefile(src):
            return
        dest.write_bytes(src.read_bytes())


def rasterize_page(pdf_path: Path, page_number: int, out_path: Path,
                   dpi: float = 144.0) -> int:
    """Render `page_number` (1-indexed) to PNG. Returns total pages in the PDF."""
    doc = fitz.open(pdf_path)
    total = doc.page_count
    if page_number < 1 or page_number > total:
        sys.exit(f"Page {page_number} out of range; PDF has {total} pages")
    page = doc.load_page(page_number - 1)
    zoom = dpi / 72.0  # pymupdf default is 72 dpi
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    pix.save(str(out_path))
    doc.close()
    return total


def render_wrapper(pdf_id: str, page: int, total: int,
                   page_image_filename: str, citation: str | None,
                   out_html: Path) -> None:
    env = Environment(
        loader=FileSystemLoader(str(RECIPES_DIR)),
        autoescape=select_autoescape(["html"]),
    )
    template = env.get_template("inline_pdf.html.j2")
    out_html.write_text(template.render(
        filename=f"{pdf_id}.pdf",
        page=page,
        total=total,
        citation=citation or "",
        page_image=page_image_filename,
    ))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--working-dir", required=True)
    ap.add_argument("--pdf-id", required=True,
                    help="Stable slug, e.g. spme_2024_09_p60")
    ap.add_argument("--pdf-source", required=True,
                    help="Local path or http(s) URL")
    ap.add_argument("--page", type=int, required=True,
                    help="1-indexed page number")
    ap.add_argument("--citation", default=None)
    args = ap.parse_args()

    wd = resolve_working_dir(args.working_dir)
    pdfs_dir = ensure_dir(wd / "_assets" / "pdfs")
    pages_dir = ensure_dir(wd / "_assets" / "pdf_pages")
    wrappers_dir = ensure_dir(wd / "_assets" / "pdf_wrappers")

    pdf_path = pdfs_dir / f"{args.pdf_id}.pdf"
    page_image_name = f"{args.pdf_id}_p{args.page}.png"
    page_path = pages_dir / page_image_name
    wrapper_path = wrappers_dir / f"{args.pdf_id}_p{args.page}.html"

    fetch_pdf(args.pdf_source, pdf_path)
    total = rasterize_page(pdf_path, args.page, page_path)

    # The wrapper sits in `_assets/pdf_wrappers/`; the image sits in
    # `_assets/pdf_pages/`. Use a relative path so the wrapper is portable.
    relative_image = f"../pdf_pages/{page_image_name}"

    render_wrapper(
        pdf_id=args.pdf_id,
        page=args.page,
        total=total,
        page_image_filename=relative_image,
        citation=args.citation,
        out_html=wrapper_path,
    )

    print(f"✓ PDF wrapper: {wrapper_path}")
    print(f"  page image:  {page_path}")
    print(f"  total pages: {total}")


if __name__ == "__main__":
    main()
