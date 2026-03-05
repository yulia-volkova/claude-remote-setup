"""Extract highlights and ink annotations from a reMarkable document directory.

Usage: uv run --python 3.12 --with rmscene,PyMuPDF extract_annotations.py <doc-dir>

The doc-dir should contain:
  - A .pdf file (the original document)
  - A .content JSON file (page mapping)
  - A subdirectory with .rm files (annotation layers)

Outputs JSON to stdout.
"""

import json
import os
import sys
from pathlib import Path

from rmscene import read_blocks, SceneGlyphItemBlock, SceneLineItemBlock


def find_files(doc_dir: Path):
    """Find the PDF, .content file, and .rm files in the document directory."""
    pdf_file = None
    content_file = None
    rm_files = []

    for f in doc_dir.rglob("*"):
        if f.suffix == ".pdf":
            pdf_file = f
        elif f.suffix == ".content":
            content_file = f
        elif f.suffix == ".rm":
            rm_files.append(f)

    return pdf_file, content_file, rm_files


def build_page_map(content_file: Path) -> dict[str, int]:
    """Map page UUIDs to page numbers from the .content file."""
    page_map = {}
    if not content_file or not content_file.exists():
        return page_map

    with open(content_file) as f:
        content = json.load(f)

    # The .content file has cPages.pages with id and redir info
    pages = content.get("cPages", {}).get("pages", [])
    if not pages:
        # Older format: just a "pages" array of UUIDs
        pages_list = content.get("pages", [])
        for i, page_id in enumerate(pages_list):
            page_map[page_id] = i
        return page_map

    for i, page in enumerate(pages):
        page_id = page.get("id", "")
        if page_id:
            page_map[page_id] = i
        # Also handle redirect mappings
        redir = page.get("redir", {})
        if isinstance(redir, dict):
            redir_val = redir.get("value", "")
            if redir_val:
                page_map[redir_val] = i

    return page_map


def extract_rm_annotations(rm_file: Path, page_num: int):
    """Extract highlights and ink strokes from a single .rm file."""
    highlights = []
    ink_annotations = []

    with open(rm_file, "rb") as f:
        blocks = list(read_blocks(f))

    for block in blocks:
        if isinstance(block, SceneGlyphItemBlock):
            value = block.item.value
            if value is None or block.item.deleted_length > 0:
                continue
            highlights.append({
                "page": page_num,
                "text": value.text,
                "color": value.color.value if hasattr(value.color, "value") else int(value.color),
                "start": value.start,
                "length": value.length,
            })
        elif isinstance(block, SceneLineItemBlock):
            value = block.item.value
            if value is None or block.item.deleted_length > 0:
                continue
            # Collect stroke bounding box for rendering
            points = value.points
            if not points:
                continue
            xs = [p.x for p in points]
            ys = [p.y for p in points]
            bbox = [min(xs), min(ys), max(xs), max(ys)]
            ink_annotations.append({
                "page": page_num,
                "bbox": bbox,
                "tool": value.tool.name if hasattr(value.tool, "name") else str(value.tool),
                "color": value.color.value if hasattr(value.color, "value") else int(value.color),
                "num_points": len(points),
            })

    return highlights, ink_annotations


def render_ink_regions(pdf_file: Path, ink_annotations: list, doc_dir: Path) -> list:
    """Render ink annotation regions as PNG images using PyMuPDF."""
    import fitz  # PyMuPDF

    if not ink_annotations or not pdf_file:
        return ink_annotations

    doc = fitz.open(str(pdf_file))

    # reMarkable page dimensions (in rm coordinate space)
    RM_WIDTH = 1404
    RM_HEIGHT = 1872

    # Group ink annotations by page to reduce page opens
    by_page = {}
    for i, ann in enumerate(ink_annotations):
        by_page.setdefault(ann["page"], []).append((i, ann))

    for page_num, anns in by_page.items():
        if page_num >= len(doc):
            continue
        page = doc[page_num]
        page_rect = page.rect

        # Scale factors from rm coords to PDF coords
        sx = page_rect.width / RM_WIDTH
        sy = page_rect.height / RM_HEIGHT

        for idx, ann in anns:
            # Convert rm bbox to PDF coordinates
            x0, y0, x1, y1 = ann["bbox"]
            margin = 20  # Add margin in rm coords
            pdf_rect = fitz.Rect(
                (x0 - margin) * sx,
                (y0 - margin) * sy,
                (x1 + margin) * sx,
                (y1 + margin) * sy,
            )
            # Clip to page bounds
            pdf_rect = pdf_rect & page_rect

            if pdf_rect.is_empty:
                continue

            # Render the region at 2x resolution
            mat = fitz.Matrix(2, 2)
            pix = page.get_pixmap(matrix=mat, clip=pdf_rect)
            img_name = f"ink_p{page_num}_{idx}.png"
            img_path = doc_dir / img_name
            pix.save(str(img_path))
            ink_annotations[idx]["image_path"] = str(img_path)

    doc.close()
    return ink_annotations


def extract_pdf_metadata(pdf_file: Path):
    """Extract metadata and links from the PDF."""
    import fitz

    doc = fitz.open(str(pdf_file))
    metadata = doc.metadata or {}

    title = metadata.get("title", "")
    author = metadata.get("author", "")
    total_pages = len(doc)

    links = []
    for page_num in range(total_pages):
        page = doc[page_num]
        for link in page.get_links():
            if link.get("uri"):
                links.append({
                    "page": page_num,
                    "uri": link["uri"],
                })

    doc.close()
    return title, author, total_pages, links


def main():
    if len(sys.argv) < 2:
        print("Usage: extract_annotations.py <doc-dir>", file=sys.stderr)
        sys.exit(1)

    doc_dir = Path(sys.argv[1])
    if not doc_dir.is_dir():
        print(f"Error: {doc_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    pdf_file, content_file, rm_files = find_files(doc_dir)
    page_map = build_page_map(content_file)

    all_highlights = []
    all_ink = []

    for rm_file in rm_files:
        # Page UUID is the .rm filename (without extension)
        page_uuid = rm_file.stem
        page_num = page_map.get(page_uuid, -1)

        # If we can't map the UUID, try to infer from directory structure
        if page_num == -1:
            # Sometimes .rm files are just numbered
            try:
                page_num = int(page_uuid)
            except ValueError:
                # Try matching by position in sorted rm_files
                page_num = sorted(rm_files).index(rm_file)

        highlights, ink = extract_rm_annotations(rm_file, page_num)
        all_highlights.extend(highlights)
        all_ink.extend(ink)

    # Extract PDF metadata and links
    title, author, total_pages, links = "", "", 0, []
    if pdf_file:
        title, author, total_pages, links = extract_pdf_metadata(pdf_file)

    # Render ink annotation regions as PNGs
    if pdf_file and all_ink:
        all_ink = render_ink_regions(pdf_file, all_ink, doc_dir)

    # Sort highlights by page number
    all_highlights.sort(key=lambda h: (h["page"], h.get("start", 0) or 0))

    result = {
        "title": title,
        "author": author,
        "total_pages": total_pages,
        "highlights": all_highlights,
        "ink_annotations": [a for a in all_ink if a.get("image_path")],
        "links": links,
    }

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
