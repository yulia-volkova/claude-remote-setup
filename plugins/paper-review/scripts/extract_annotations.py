"""Extract highlights and ink annotations from a reMarkable document directory.

Usage: uv run --python 3.12 --with rmscene,PyMuPDF,Pillow,pyobjc-framework-Vision extract_annotations.py <doc-dir>

The doc-dir should contain:
  - A .pdf file (the original document)
  - A .content JSON file (page mapping)
  - A subdirectory with .rm files (annotation layers)

Outputs JSON to stdout. Saves ink cluster PNGs to doc-dir.
"""

import json
import sys
from pathlib import Path

from rmscene import read_blocks, SceneGlyphItemBlock, SceneLineItemBlock
from rmscene.scene_items import PenColor, Pen

# reMarkable page dimensions (rm coordinate space)
RM_WIDTH = 1404
RM_HEIGHT = 1872

# --- Color and tool mappings ---

PEN_COLOR_MAP = {
    PenColor.BLACK.value: "black",
    PenColor.GRAY.value: "gray",
    PenColor.WHITE.value: "white",
    PenColor.YELLOW.value: "yellow",
    PenColor.GREEN.value: "green",
    PenColor.PINK.value: "pink",
    PenColor.BLUE.value: "blue",
    PenColor.RED.value: "red",
    PenColor.GRAY_OVERLAP.value: "gray",
    PenColor.HIGHLIGHT.value: "yellow",
    PenColor.GREEN_2.value: "green",
    PenColor.CYAN.value: "cyan",
    PenColor.MAGENTA.value: "magenta",
    PenColor.YELLOW_2.value: "yellow",
}

PEN_COLOR_RGB = {
    PenColor.BLACK.value: (0, 0, 0),
    PenColor.GRAY.value: (125, 125, 125),
    PenColor.WHITE.value: (200, 200, 200),
    PenColor.YELLOW.value: (251, 205, 50),
    PenColor.GREEN.value: (0, 160, 60),
    PenColor.PINK.value: (220, 50, 120),
    PenColor.BLUE.value: (0, 100, 220),
    PenColor.RED.value: (220, 40, 40),
    PenColor.GRAY_OVERLAP.value: (125, 125, 125),
    PenColor.HIGHLIGHT.value: (251, 205, 50),
    PenColor.GREEN_2.value: (0, 160, 60),
    PenColor.CYAN.value: (0, 180, 210),
    PenColor.MAGENTA.value: (180, 40, 180),
    PenColor.YELLOW_2.value: (251, 205, 50),
}

PEN_TOOL_MAP = {
    Pen.BALLPOINT_1.value: "Ballpoint",
    Pen.BALLPOINT_2.value: "Ballpoint",
    Pen.CALIGRAPHY.value: "Calligraphy",
    Pen.ERASER.value: "Eraser",
    Pen.ERASER_AREA.value: "Eraser",
    Pen.FINELINER_1.value: "Fineliner",
    Pen.FINELINER_2.value: "Fineliner",
    Pen.HIGHLIGHTER_1.value: "Highlighter",
    Pen.HIGHLIGHTER_2.value: "Highlighter",
    Pen.MARKER_1.value: "Marker",
    Pen.MARKER_2.value: "Marker",
    Pen.MECHANICAL_PENCIL_1.value: "Mechanical Pencil",
    Pen.MECHANICAL_PENCIL_2.value: "Mechanical Pencil",
    Pen.PAINTBRUSH_1.value: "Paintbrush",
    Pen.PAINTBRUSH_2.value: "Paintbrush",
    Pen.PENCIL_1.value: "Pencil",
    Pen.PENCIL_2.value: "Pencil",
    Pen.SHADER.value: "Shader",
}

ERASER_TOOLS = {Pen.ERASER.value, Pen.ERASER_AREA.value}


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

    pages = content.get("cPages", {}).get("pages", [])
    if not pages:
        pages_list = content.get("pages", [])
        for i, page_id in enumerate(pages_list):
            page_map[page_id] = i
        return page_map

    for i, page in enumerate(pages):
        page_id = page.get("id", "")
        if page_id:
            page_map[page_id] = i
        redir = page.get("redir", {})
        if isinstance(redir, dict):
            redir_val = redir.get("value", "")
            if redir_val:
                page_map[redir_val] = i

    return page_map


def extract_rm_annotations(rm_file: Path, page_num: int):
    """Extract highlights and ink strokes from a single .rm file.

    Returns (highlights, strokes) where strokes include raw point data.
    """
    highlights = []
    strokes = []

    with open(rm_file, "rb") as f:
        blocks = list(read_blocks(f))

    for block in blocks:
        if isinstance(block, SceneGlyphItemBlock):
            value = block.item.value
            if value is None or block.item.deleted_length > 0:
                continue
            color_val = value.color.value if hasattr(value.color, "value") else int(value.color)
            highlights.append({
                "page": page_num,
                "text": value.text,
                "color": color_val,
                "color_name": PEN_COLOR_MAP.get(color_val, "unknown"),
                "start": value.start,
                "length": value.length,
            })
        elif isinstance(block, SceneLineItemBlock):
            value = block.item.value
            if value is None or block.item.deleted_length > 0:
                continue
            points = value.points
            if not points:
                continue
            xs = [p.x for p in points]
            ys = [p.y for p in points]
            tool_val = value.tool.value if hasattr(value.tool, "value") else int(value.tool)
            color_val = value.color.value if hasattr(value.color, "value") else int(value.color)
            strokes.append({
                "page": page_num,
                "bbox": [min(xs), min(ys), max(xs), max(ys)],
                "tool": tool_val,
                "tool_name": PEN_TOOL_MAP.get(tool_val, "Unknown"),
                "color": color_val,
                "color_name": PEN_COLOR_MAP.get(color_val, "unknown"),
                "thickness_scale": value.thickness_scale,
                "points": [(p.x, p.y, p.width, p.pressure) for p in points],
            })

    return highlights, strokes


# --- Union-Find for clustering ---

class UnionFind:
    def __init__(self, n):
        self.parent = list(range(n))
        self.rank = [0] * n

    def find(self, x):
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if self.rank[ra] < self.rank[rb]:
            ra, rb = rb, ra
        self.parent[rb] = ra
        if self.rank[ra] == self.rank[rb]:
            self.rank[ra] += 1


def bbox_gap(a, b):
    """Compute edge-to-edge distance between two bboxes [x0, y0, x1, y1]."""
    dx = max(0, max(a[0], b[0]) - min(a[2], b[2]))
    dy = max(0, max(a[1], b[1]) - min(a[3], b[3]))
    return (dx * dx + dy * dy) ** 0.5


def cluster_strokes(strokes, gap_threshold=60.0):
    """Group strokes on the same page into logical handwritten notes.

    Uses Union-Find on bounding box proximity. Two strokes merge if
    their bbox edge-to-edge distance < gap_threshold.
    Filters out eraser strokes and stray marks (<5 total points).
    """
    draw_strokes = [s for s in strokes if s["tool"] not in ERASER_TOOLS]
    if not draw_strokes:
        return []

    by_page = {}
    for s in draw_strokes:
        by_page.setdefault(s["page"], []).append(s)

    clusters = []
    for page_num, page_strokes in sorted(by_page.items()):
        n = len(page_strokes)
        uf = UnionFind(n)

        for i in range(n):
            for j in range(i + 1, n):
                if bbox_gap(page_strokes[i]["bbox"], page_strokes[j]["bbox"]) < gap_threshold:
                    uf.union(i, j)

        groups = {}
        for i in range(n):
            root = uf.find(i)
            groups.setdefault(root, []).append(page_strokes[i])

        for cluster_id, group in enumerate(groups.values()):
            total_points = sum(len(s["points"]) for s in group)
            if total_points < 5:
                continue

            x0 = min(s["bbox"][0] for s in group)
            y0 = min(s["bbox"][1] for s in group)
            x1 = max(s["bbox"][2] for s in group)
            y1 = max(s["bbox"][3] for s in group)

            is_full_page = (x1 - x0) > 1200 and (y1 - y0) > 1600

            colors = sorted(set(s["color_name"] for s in group))
            tools = sorted(set(s["tool_name"] for s in group))

            clusters.append({
                "page": page_num,
                "cluster_id": cluster_id,
                "bbox": [x0, y0, x1, y1],
                "num_strokes": len(group),
                "total_points": total_points,
                "type": "full-page" if is_full_page else "note",
                "stroke_colors": colors,
                "tools_used": tools,
                "strokes": group,
            })

    return clusters


def render_cluster_white(cluster, doc_dir: Path, padding=30, scale=2.0):
    """Draw all strokes in a cluster on a white background."""
    from PIL import Image, ImageDraw

    x0, y0, x1, y1 = cluster["bbox"]
    w = max(10, int((x1 - x0) * scale + 2 * padding))
    h = max(10, int((y1 - y0) * scale + 2 * padding))

    img = Image.new("RGB", (w, h), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    for stroke in cluster["strokes"]:
        pts = stroke["points"]
        if len(pts) < 2:
            continue
        color = PEN_COLOR_RGB.get(stroke["color"], (0, 0, 0))
        line_width = max(1, int(stroke["thickness_scale"] * scale))

        coords = [
            (int((p[0] - x0) * scale + padding), int((p[1] - y0) * scale + padding))
            for p in pts
        ]
        draw.line(coords, fill=color, width=line_width)

    page = cluster["page"]
    cid = cluster["cluster_id"]
    name = f"ink_cluster_p{page}_{cid}_white.png"
    path = doc_dir / name
    img.save(str(path))
    return str(path)


def render_cluster_context(cluster, pdf_file: Path, doc_dir: Path):
    """Draw strokes overlaid on PDF background."""
    import fitz
    from PIL import Image, ImageDraw

    page_num = cluster["page"]
    x0, y0, x1, y1 = cluster["bbox"]

    doc = fitz.open(str(pdf_file))
    if page_num >= len(doc):
        doc.close()
        return None

    page = doc[page_num]
    page_rect = page.rect
    sx = page_rect.width / RM_WIDTH
    sy = page_rect.height / RM_HEIGHT

    margin_rm = 40
    # Clip region in PDF coords (clamp to page bounds)
    clip_x0 = max(0, (x0 - margin_rm) * sx)
    clip_y0 = max(0, (y0 - margin_rm) * sy)
    clip_x1 = min(page_rect.width, (x1 + margin_rm) * sx)
    clip_y1 = min(page_rect.height, (y1 + margin_rm) * sy)

    pdf_rect = fitz.Rect(clip_x0, clip_y0, clip_x1, clip_y1)
    if pdf_rect.is_empty:
        doc.close()
        return None

    mat = fitz.Matrix(2, 2)
    pix = page.get_pixmap(matrix=mat, clip=pdf_rect)
    bg = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)

    # If strokes extend into negative x (margin notes), add gray canvas on left
    left_extend = 0
    if x0 < 0:
        left_extend_rm = abs(x0) + margin_rm
        left_extend = int(left_extend_rm * sx * 2)
        extended = Image.new("RGB", (bg.width + left_extend, bg.height), (230, 230, 230))
        extended.paste(bg, (left_extend, 0))
        bg = extended

    overlay = Image.new("RGBA", bg.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Origin of the clip region in rm coords
    origin_x = max(x0 - margin_rm, 0) if x0 >= 0 else 0
    origin_y = max(y0 - margin_rm, 0)

    for stroke in cluster["strokes"]:
        pts = stroke["points"]
        if len(pts) < 2:
            continue
        rgb = PEN_COLOR_RGB.get(stroke["color"], (0, 0, 0))
        alpha = 140 if stroke["tool_name"] == "Highlighter" else 220
        color = (*rgb, alpha)
        line_width = max(1, int(stroke["thickness_scale"] * sx * 2))

        coords = []
        for p in pts:
            # Convert rm coords to pixel coords in the rendered image
            px = (p[0] - origin_x) * sx * 2 + left_extend
            py = (p[1] - origin_y) * sy * 2
            coords.append((int(px), int(py)))

        draw.line(coords, fill=color, width=line_width)

    bg_rgba = bg.convert("RGBA")
    composite = Image.alpha_composite(bg_rgba, overlay)
    result = composite.convert("RGB")

    cid = cluster["cluster_id"]
    name = f"ink_cluster_p{page_num}_{cid}_context.png"
    path = doc_dir / name
    result.save(str(path))
    doc.close()
    return str(path)


def extract_surrounding_text(pdf_file: Path, page_num: int, bbox, expansion=100):
    """Extract PDF text near a cluster using PyMuPDF."""
    import fitz

    doc = fitz.open(str(pdf_file))
    if page_num >= len(doc):
        doc.close()
        return ""

    page = doc[page_num]
    page_rect = page.rect
    sx = page_rect.width / RM_WIDTH
    sy = page_rect.height / RM_HEIGHT

    x0, y0, x1, y1 = bbox
    clip = fitz.Rect(
        max(0, (x0 - expansion) * sx),
        max(0, (y0 - expansion) * sy),
        min(page_rect.width, (x1 + expansion) * sx),
        min(page_rect.height, (y1 + expansion) * sy),
    )

    text = page.get_text(clip=clip).strip()
    doc.close()

    if len(text) > 500:
        text = text[:500] + "..."
    return text


def transcribe_image(image_path: str) -> str:
    """Transcribe handwriting from a PNG using macOS Vision framework.

    Returns recognized text or empty string on failure/non-macOS.
    """
    try:
        import Vision
        from Quartz import (
            CGImageSourceCreateWithURL,
            CGImageSourceCreateImageAtIndex,
        )
        from Foundation import NSURL
    except ImportError:
        return ""

    try:
        url = NSURL.fileURLWithPath_(image_path)
        source = CGImageSourceCreateWithURL(url, None)
        if source is None:
            return ""
        cg_image = CGImageSourceCreateImageAtIndex(source, 0, None)
        if cg_image is None:
            return ""

        request = Vision.VNRecognizeTextRequest.alloc().init()
        request.setRecognitionLevel_(0)  # 0 = accurate
        handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(
            cg_image, None
        )
        success = handler.performRequests_error_([request], None)
        if not success[0]:
            return ""

        results = request.results()
        if not results:
            return ""

        lines = []
        for obs in results:
            candidate = obs.topCandidates_(1)
            if candidate:
                lines.append(candidate[0].string())
        return "\n".join(lines)
    except Exception:
        return ""


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
    all_strokes = []

    for rm_file in rm_files:
        page_uuid = rm_file.stem
        page_num = page_map.get(page_uuid, -1)

        if page_num == -1:
            try:
                page_num = int(page_uuid)
            except ValueError:
                page_num = sorted(rm_files).index(rm_file)

        highlights, strokes = extract_rm_annotations(rm_file, page_num)
        all_highlights.extend(highlights)
        all_strokes.extend(strokes)

    # Cluster strokes into logical handwritten notes
    clusters = cluster_strokes(all_strokes)

    # Render cluster images and extract surrounding text
    handwritten_notes = []
    for cluster in clusters:
        if cluster["type"] == "full-page":
            continue

        white_path = render_cluster_white(cluster, doc_dir)
        context_path = None
        surrounding_text = ""
        transcription = transcribe_image(white_path) if white_path else ""

        if pdf_file:
            context_path = render_cluster_context(cluster, pdf_file, doc_dir)
            surrounding_text = extract_surrounding_text(
                pdf_file, cluster["page"], cluster["bbox"]
            )

        note = {
            "page": cluster["page"],
            "cluster_id": cluster["cluster_id"],
            "bbox": cluster["bbox"],
            "num_strokes": cluster["num_strokes"],
            "ink_on_white_path": white_path,
            "ink_on_pdf_path": context_path,
            "surrounding_text": surrounding_text,
            "transcription": transcription,
            "stroke_colors": cluster["stroke_colors"],
            "tools_used": cluster["tools_used"],
        }
        handwritten_notes.append(note)

    # Extract PDF metadata and links
    title, author, total_pages, links = "", "", 0, []
    if pdf_file:
        title, author, total_pages, links = extract_pdf_metadata(pdf_file)

    # Sort highlights by page number
    all_highlights.sort(key=lambda h: (h["page"], h.get("start", 0) or 0))

    result = {
        "title": title,
        "author": author,
        "total_pages": total_pages,
        "highlights": all_highlights,
        "handwritten_notes": handwritten_notes,
        "links": links,
    }

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
