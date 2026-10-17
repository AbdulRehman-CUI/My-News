"""PDF export from immutable edition snapshots."""
from pathlib import Path
from flask import render_template


def pdf_revision(edition):
    return edition["generated_at"].replace(":", "").replace("+", "").replace("Z", "z")


def cached_pdf_path(root, edition):
    cache = Path(root) / "generated"
    cache.mkdir(parents=True, exist_ok=True)
    return cache / f"{edition['id']}-{pdf_revision(edition)}.pdf"


def export_pdf(root, edition, items):
    path = cached_pdf_path(root, edition)
    if path.is_file() and path.stat().st_size:
        return path.read_bytes(), True
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "PDF export requires Playwright. Install requirements.txt and run "
            "python -m playwright install chromium."
        ) from exc
    html = render_template("newspaper.html", edition=edition, items=items)
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page()
            page.set_content(html, wait_until="load")
            payload = page.pdf(
                format="A4", print_background=True, display_header_footer=True,
                margin={"top": "16mm", "right": "14mm", "bottom": "16mm", "left": "14mm"},
                header_template="<span></span>",
                footer_template='<div class="page-footer">MyNews · Page <span class="pageNumber"></span> of <span class="totalPages"></span></div>',
            )
            browser.close()
    except Exception as exc:
        raise RuntimeError(f"PDF export failed: {type(exc).__name__}: {str(exc)[:180]}") from exc
    path.write_bytes(payload)
    return payload, False
