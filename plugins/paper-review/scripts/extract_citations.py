"""Extract citations, URLs, DOIs, and arXiv IDs from a PDF.

Usage: uv run --python 3.12 --with PyMuPDF extract_citations.py <pdf-path>

Outputs JSON to stdout.
"""

import json
import re
import sys
from pathlib import Path


def extract_text(pdf_path: Path) -> str:
    """Extract full text from PDF."""
    import fitz

    doc = fitz.open(str(pdf_path))
    text = ""
    for page in doc:
        text += page.get_text() + "\n"
    doc.close()
    return text


def extract_urls(text: str) -> list[str]:
    """Extract unique URLs from text."""
    pattern = r'https?://[^\s\)\]\}>,;"\']+[^\s\)\]\}>,;"\'\.]'
    urls = re.findall(pattern, text)
    # Deduplicate while preserving order
    seen = set()
    unique = []
    for url in urls:
        if url not in seen:
            seen.add(url)
            unique.append(url)
    return unique


def extract_dois(text: str) -> list[str]:
    """Extract unique DOIs from text."""
    pattern = r'(?:doi(?:\.org)?[:/]\s*|DOI[:/]\s*)?(?:https?://(?:dx\.)?doi\.org/)?(10\.\d{4,}/[^\s,;\]\)]+[^\s,;\]\)\.])'
    matches = re.findall(pattern, text)
    seen = set()
    unique = []
    for doi in matches:
        doi = doi.rstrip(".")
        if doi not in seen:
            seen.add(doi)
            unique.append(doi)
    return unique


def extract_arxiv_ids(text: str) -> list[str]:
    """Extract unique arXiv IDs from text."""
    # Modern format: YYMM.NNNNN
    pattern = r'(?:arXiv:?\s*)?(\d{4}\.\d{4,5})(?:v\d+)?'
    matches = re.findall(pattern, text)
    seen = set()
    unique = []
    for arxiv_id in matches:
        if arxiv_id not in seen:
            seen.add(arxiv_id)
            unique.append(arxiv_id)
    return unique


def extract_references(text: str) -> list[dict]:
    """Extract numbered references from the References section."""
    # Find the References section
    ref_match = re.search(r'\n\s*(?:References|REFERENCES|Bibliography)\s*\n', text)
    if not ref_match:
        return []

    ref_text = text[ref_match.end():]

    # Match numbered references like [1], [2], etc.
    entries = re.split(r'\n\s*\[(\d+)\]\s*', ref_text)

    references = []
    # entries[0] is text before first [N], then alternating: number, text
    for i in range(1, len(entries) - 1, 2):
        num = entries[i]
        body = entries[i + 1].strip()
        # Clean up: collapse whitespace, limit length
        body = re.sub(r'\s+', ' ', body)
        if len(body) > 500:
            body = body[:500] + "..."
        if body:
            references.append({"number": int(num), "text": body})

    return references


def main():
    if len(sys.argv) < 2:
        print("Usage: extract_citations.py <pdf-path>", file=sys.stderr)
        sys.exit(1)

    pdf_path = Path(sys.argv[1])
    if not pdf_path.exists():
        print(f"Error: {pdf_path} does not exist", file=sys.stderr)
        sys.exit(1)

    text = extract_text(pdf_path)
    result = {
        "urls": extract_urls(text),
        "dois": extract_dois(text),
        "arxiv_ids": extract_arxiv_ids(text),
        "references": extract_references(text),
    }

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
