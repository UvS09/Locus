from __future__ import annotations


def _escape_pdf_text(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def build_pdf_report(*, title: str, lines: list[str]) -> bytes:
    page_height = 792
    top_margin = 752
    line_height = 16
    max_lines_per_page = 42

    objects: list[bytes] = []

    def add_object(payload: str | bytes) -> int:
        data = payload.encode("latin-1") if isinstance(payload, str) else payload
        objects.append(data)
        return len(objects)

    font_id = add_object("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    content_ids: list[int] = []
    page_ids: list[int] = []
    pages: list[list[str]] = [lines[index:index + max_lines_per_page] for index in range(0, len(lines), max_lines_per_page)] or [[]]

    for page_number, page_lines in enumerate(pages, start=1):
        stream_lines = [
            "BT",
            "/F1 18 Tf",
            f"50 {top_margin} Td",
            f"({_escape_pdf_text(title)}{f' - Page {page_number}' if len(pages) > 1 else ''}) Tj",
            "/F1 11 Tf",
        ]
        current_y = top_margin - 28
        for line in page_lines:
            safe_line = _escape_pdf_text(line)
            stream_lines.append(f"1 0 0 1 50 {current_y} Tm")
            stream_lines.append(f"({safe_line}) Tj")
            current_y -= line_height
        stream_lines.append("ET")
        stream = "\n".join(stream_lines).encode("latin-1", errors="ignore")
        content_id = add_object(b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream")
        content_ids.append(content_id)
        page_ids.append(0)

    pages_id = add_object("")
    for index, content_id in enumerate(content_ids):
        page_id = add_object(
            f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 612 {page_height}] "
            f"/Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {content_id} 0 R >>"
        )
        page_ids[index] = page_id

    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    objects[pages_id - 1] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode("latin-1")
    catalog_id = add_object(f"<< /Type /Catalog /Pages {pages_id} 0 R >>")

    pdf = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for obj_id, payload in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{obj_id} 0 obj\n".encode("latin-1"))
        pdf.extend(payload)
        pdf.extend(b"\nendobj\n")

    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("latin-1"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("latin-1"))
    pdf.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_id} 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF"
        ).encode("latin-1")
    )
    return bytes(pdf)
