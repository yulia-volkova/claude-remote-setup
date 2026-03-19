"""Extract highlights and ink annotations from a Notability-exported PDF.

Usage: uv run --python 3.12 --with PyMuPDF,Pillow,pyobjc-framework-Vision extract_notability_annotations.py <pdf-path>

Notability exports annotated PDFs with standard PDF annotation layers:
  - Highlight annotations (type /Highlight) contain highlighted text regions
  - Ink annotations (type /Ink) contain handwritten notes as stroke paths

Outputs JSON to stdout in the same format as extract_annotations.py:
  {highlights: [...], handwritten_notes: [...], metadata: {...}}
"""

import json
import sys
from pathlib import Path


def extract_highlights(page, page_num):
    """Extract highlight annotations from a PDF page."""
    highlights = []
    annots = page.annots()
    if not annots:
        return highlights

    for annot in annots:
        if annot.type[0] != 8:  # 8 = Highlight annotation type
            continue

        rect = annot.rect
        # Extract the text under the highlight region
        text = page.get_text(clip=rect).strip()
        if not text:
            continue

        # Get highlight color from annotation
        colors = annot.colors
        stroke_color = colors.get("stroke", (1, 1, 0))  # default yellow
        color_name = _rgb_to_color_name(stroke_color)

        highlights.append({
            "page": page_num,
            "text": text,
            "color": list(stroke_color),
            "color_name": color_name,
            "rect": [rect.x0, rect.y0, rect.x1, rect.y1],
        })

    return highlights


def _rgb_to_color_name(rgb):
    """Map an RGB tuple (0-1 range) to a human-readable color name."""
    if len(rgb) < 3:
        return "unknown"
    r, g, b = rgb[0], rgb[1], rgb[2]

    color_map = [
        ((1.0, 1.0, 0.0), "yellow"),
        ((0.0, 1.0, 0.0), "green"),
        ((1.0, 0.0, 0.0), "red"),
        ((0.0, 0.0, 1.0), "blue"),
        ((1.0, 0.0, 1.0), "pink"),
        ((1.0, 0.5, 0.0), "orange"),
        ((0.0, 1.0, 1.0), "cyan"),
    ]

    best_name = "yellow"
    best_dist = float("inf")
    for ref, name in color_map:
        dist = (r - ref[0]) ** 2 + (g - ref[1]) ** 2 + (b - ref[2]) ** 2
        if dist < best_dist:
            best_dist = dist
            best_name = name

    return best_name


def extract_ink_annotations(page, page_num):
    """Extract ink (handwritten) annotations from a PDF page.

    Returns raw ink annotation data with bounding boxes and vertices.
    """
    ink_annots = []
    annots = page.annots()
    if not annots:
        return ink_annots

    for annot in annots:
        if annot.type[0] != 15:  # 15 = Ink annotation type
            continue

        rect = annot.rect
        vertices = annot.vertices
        colors = annot.colors
        stroke_color = colors.get("stroke", (0, 0, 0))

        ink_annots.append({
            "page": page_num,
            "rect": [rect.x0, rect.y0, rect.x1, rect.y1],
            "vertices": [(v.x, v.y) for v in vertices] if vertices else [],
            "color": list(stroke_color),
            "color_name": _rgb_to_color_name(stroke_color),
            "width": annot.border.get("width", 1.0) if annot.border else 1.0,
        })

    return ink_annots


def cluster_ink_annotations(ink_annots, gap_threshold=30.0):
    """Group nearby ink annotations into logical handwritten notes.

    Uses simple proximity clustering on bounding boxes.
    """
    if not ink_annots:
        return []

    by_page = {}
    for annot in ink_annots:
        by_page.setdefault(annot["page"], []).append(annot)

    clusters = []
    for page_num, page_annots in sorted(by_page.items()):
        # Simple greedy clustering by bbox proximity
        used = [False] * len(page_annots)
        for i, annot in enumerate(page_annots):
            if used[i]:
                continue
            group = [annot]
            used[i] = True
            # Find all nearby annotations
            changed = True
            while changed:
                changed = False
                for j, other in enumerate(page_annots):
                    if used[j]:
                        continue
                    # Check if close to any annotation in the group
                    for member in group:
                        if _bbox_gap(member["rect"], other["rect"]) < gap_threshold:
                            group.append(other)
                            used[j] = True
                            changed = True
                            break

            # Compute cluster bounding box
            x0 = min(a["rect"][0] for a in group)
            y0 = min(a["rect"][1] for a in group)
            x1 = max(a["rect"][2] for a in group)
            y1 = max(a["rect"][3] for a in group)

            colors = sorted(set(a["color_name"] for a in group))
            cluster_id = len(clusters)

            clusters.append({
                "page": page_num,
                "cluster_id": cluster_id,
                "bbox": [x0, y0, x1, y1],
                "num_strokes": len(group),
                "stroke_colors": colors,
                "tools_used": ["Pen"],
                "ink_annotations": group,
            })

    return clusters


def _bbox_gap(a, b):
    """Compute edge-to-edge distance between two bboxes [x0, y0, x1, y1]."""
    dx = max(0, max(a[0], b[0]) - min(a[2], b[2]))
    dy = max(0, max(a[1], b[1]) - min(a[3], b[3]))
    return (dx * dx + dy * dy) ** 0.5


def render_cluster_white(cluster, output_dir, doc, padding=20, scale=2.0):
    """Render ink cluster strokes on a white background for OCR."""
    from PIL import Image, ImageDraw

    bbox = cluster["bbox"]
    x0, y0, x1, y1 = bbox
    w = max(10, int((x1 - x0) * scale + 2 * padding))
    h = max(10, int((y1 - y0) * scale + 2 * padding))

    img = Image.new("RGB", (w, h), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    for annot in cluster["ink_annotations"]:
        verts = annot.get("vertices", [])
        if len(verts) < 2:
            continue
        color_rgb = tuple(int(c * 255) for c in annot["color"][:3])
        coords = [
            (int((v[0] - x0) * scale + padding), int((v[1] - y0) * scale + padding))
            for v in verts
        ]
        line_width = max(1, int(annot.get("width", 1.0) * scale))
        draw.line(coords, fill=color_rgb, width=line_width)

    page = cluster["page"]
    cid = cluster["cluster_id"]
    name = f"ink_cluster_p{page}_{cid}_white.png"
    path = output_dir / name
    img.save(str(path))
    return str(path)


def render_cluster_context(cluster, doc, output_dir):
    """Render ink cluster overlaid on the PDF page region."""
    import fitz
    from PIL import Image, ImageDraw

    page_num = cluster["page"]
    if page_num >= len(doc):
        return None

    page = doc[page_num]
    bbox = cluster["bbox"]
    x0, y0, x1, y1 = bbox

    margin = 30
    clip = fitz.Rect(
        max(0, x0 - margin),
        max(0, y0 - margin),
        min(page.rect.width, x1 + margin),
        min(page.rect.height, y1 + margin),
    )
    if clip.is_empty:
        return None

    mat = fitz.Matrix(2, 2)
    pix = page.get_pixmap(matrix=mat, clip=clip)
    bg = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)

    overlay = Image.new("RGBA", bg.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    origin_x = clip.x0
    origin_y = clip.y0

    for annot in cluster["ink_annotations"]:
        verts = annot.get("vertices", [])
        if len(verts) < 2:
            continue
        rgb = tuple(int(c * 255) for c in annot["color"][:3])
        color = (*rgb, 200)
        line_width = max(1, int(annot.get("width", 1.0) * 2))
        coords = [
            (int((v[0] - origin_x) * 2), int((v[1] - origin_y) * 2))
            for v in verts
        ]
        draw.line(coords, fill=color, width=line_width)

    bg_rgba = bg.convert("RGBA")
    composite = Image.alpha_composite(bg_rgba, overlay)
    result = composite.convert("RGB")

    cid = cluster["cluster_id"]
    name = f"ink_cluster_p{page_num}_{cid}_context.png"
    path = output_dir / name
    result.save(str(path))
    return str(path)


def transcribe_image(image_path):
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


def extract_surrounding_text(page, bbox, expansion=50):
    """Extract PDF text near an ink cluster."""
    import fitz

    x0, y0, x1, y1 = bbox
    clip = fitz.Rect(
        max(0, x0 - expansion),
        max(0, y0 - expansion),
        x1 + expansion,
        y1 + expansion,
    )
    text = page.get_text(clip=clip).strip()
    if len(text) > 500:
        text = text[:500] + "..."
    return text


def main():
    if len(sys.argv) < 2:
        print("Usage: extract_notability_annotations.py <pdf-path>", file=sys.stderr)
        sys.exit(1)

    pdf_path = Path(sys.argv[1])
    if not pdf_path.exists():
        print(f"Error: {pdf_path} does not exist", file=sys.stderr)
        sys.exit(1)

    import fitz

    doc = fitz.open(str(pdf_path))
    output_dir = pdf_path.parent

    all_highlights = []
    all_ink = []

    for page_num in range(len(doc)):
        page = doc[page_num]
        all_highlights.extend(extract_highlights(page, page_num))
        all_ink.extend(extract_ink_annotations(page, page_num))

    # Cluster ink annotations into logical notes
    clusters = cluster_ink_annotations(all_ink)

    # Render cluster images and extract surrounding text + transcriptions
    handwritten_notes = []
    for cluster in clusters:
        page = doc[cluster["page"]]
        white_path = render_cluster_white(cluster, output_dir, doc)
        context_path = render_cluster_context(cluster, doc, output_dir)
        surrounding_text = extract_surrounding_text(page, cluster["bbox"])
        transcription = transcribe_image(white_path) if white_path else ""

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

    # Sort highlights by page
    all_highlights.sort(key=lambda h: (h["page"], h.get("rect", [0])[1] if h.get("rect") else 0))

    # PDF metadata
    metadata = doc.metadata or {}
    title = metadata.get("title", "")
    author = metadata.get("author", "")

    result = {
        "title": title,
        "author": author,
        "total_pages": len(doc),
        "highlights": all_highlights,
        "handwritten_notes": handwritten_notes,
        "links": [],
    }

    doc.close()
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
