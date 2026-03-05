# Paper Review Plugin

Interactive 3-stage paper review workflow: Understand → Quiz → Next Steps.

## Architecture

- **Plugin root**: `${CLAUDE_PLUGIN_ROOT}` (this directory)
- **Data repo**: `/Users/titus/pyg/paper-review/` — reviews, database, downloaded papers
- **Scripts**: Run via `uv run --python 3.12 --with <deps>` (system Python is 3.9.6, rmscene needs ≥3.10)

## Scripts

- `scripts/extract_annotations.py <doc-dir>` — Parse .rm v6 files with rmscene, extract highlights and ink annotations
- `scripts/extract_citations.py <pdf-path>` — Extract URLs, DOIs, arXiv IDs from PDF text
- `scripts/resolve_citation.py <identifier>` — Look up citation metadata via Semantic Scholar/CrossRef

## reMarkable Integration

- `rmapi get` downloads .zip (NOT `rmapi geta` which fails)
- Unzip to get PDF + .rm annotation files
- .rm v6 files parsed by rmscene: `SceneGlyphItemBlock` for highlights, `SceneLineItemBlock` for ink
- Ink annotations rendered as PNGs for Claude's vision to transcribe

## Spaced Repetition

Schedule: [1, 3, 7, 14, 30, 90] days. Tracked in `database.json`.
