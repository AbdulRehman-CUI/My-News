"""PDF export from immutable edition snapshots."""
from pathlib import Path
from flask import render_template


def _pdf_escape(value):
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace("(", "\\(")
        .replace(")", "\\)")
        .replace("\r", " ")
        .replace("\n", " ")
    )


def _fallback_pdf(edition, items):
    lines = [f"MyNews — {edition['local_date']}"]
    for index, item in enumerate(items, start=1):
        lines.append(f"{index}. {item['title']}")
        brief = (item["brief"] or "").strip()
        if brief:
            lines.append(brief[:180])
        if len(lines) >= 44:
            break
    text = ["BT", "/F1 11 Tf", "50 800 Td"]
    first, rest = lines[0], lines[1:]
    text.append(f"({_pdf_escape(first)}) Tj")
    for line in rest:
        text.append(f"0 -16 Td ({_pdf_escape(line)}) Tj")
    text.append("ET")
    stream = "\n".join(text).encode("latin-1", "replace")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    payload = bytearray(b"%PDF-1.4\n")
    offsets = []
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(payload))
        payload.extend(f"{index} 0 obj\n".encode("ascii"))
        payload.extend(obj)
        payload.extend(b"\nendobj\n")
    xref_offset = len(payload)
    payload.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    payload.extend(b"0000000000 65535 f \n")
    for offset in offsets:
        payload.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    payload.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("ascii")
    )
    return bytes(payload)


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
        html = render_template("newspaper.html", edition=edition, items=items)
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
    except Exception:
        payload = _fallback_pdf(edition, items)
    path.write_bytes(payload)
    return payload, False
