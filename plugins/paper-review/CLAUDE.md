# Paper Review Plugin

Interactive 5-stage paper review workflow: Understand -> Quiz -> Wrap Up -> Spaced Repetition -> Plan Tomorrow.

## Architecture

- **Plugin root**: `${CLAUDE_PLUGIN_ROOT}` (this directory)
- **Data repo**: `/Users/yuliav/study-notes/` — reviews, database, downloaded papers
- **Scripts**: Run via `uv run --python 3.12 --with <deps>` (system Python is 3.9.6, rmscene needs >=3.10)

## Scripts

- `scripts/extract_notability_annotations.py <pdf-path>` — Extract highlights and ink annotations from Notability-exported PDFs. Deps: `PyMuPDF,Pillow,pyobjc-framework-Vision`
- `scripts/extract_annotations.py <doc-dir>` — Parse reMarkable .rm v6 files (legacy). Deps: `rmscene,PyMuPDF,Pillow`
- `scripts/extract_citations.py <pdf-path>` — Extract URLs, DOIs, arXiv IDs from PDF text
- `scripts/resolve_citation.py <identifier>` — Look up citation metadata via Semantic Scholar/CrossRef
- `scripts/sr_priority.py <database.json>` — SM-2 priority queue: outputs JSON array of papers due for review, sorted by priority

## Notability Integration

- Read papers on iPad in Notability, annotate with highlights + handwritten notes
- Export as PDF to Mac (AirDrop or iCloud), then `/paper-review ~/Downloads/exported-paper.pdf`
- `extract_notability_annotations.py` extracts standard PDF annotation layers:
  - Highlight annotations (type 8) -- text highlights with color
  - Ink annotations (type 15) -- handwritten strokes, clustered by proximity
- Ink clusters render two PNGs: `ink_cluster_p{page}_{id}_white.png` (white bg, for OCR) and `ink_cluster_p{page}_{id}_context.png` (overlaid on PDF)
- Output JSON uses `handwritten_notes` key with fields: `ink_on_white_path`, `ink_on_pdf_path`, `surrounding_text`, `transcription`, `stroke_colors`, `tools_used`
- macOS Vision framework OCR transcribes handwritten notes; Claude vision as fallback
- Dependencies: `PyMuPDF`, `Pillow`, `pyobjc-framework-Vision` (macOS)

## Spaced Repetition (SM-2)

Per-paper state in `database.json`:
- `easiness_factor` (default 2.5) — SM-2 EF, minimum 1.3
- `interval_days` — current interval between reviews
- `repetition_number` — consecutive successful reviews
- `quality_history` — array of SM-2 quality scores (0-5) from each review

Quiz score maps to quality: 90%+=5, 70%+=4, 50%+=3, 30%+=2, 10%+=1, <10%=0.
Pass (q>=3): interval grows by EF. Fail (q<2): reset to 1 day.
