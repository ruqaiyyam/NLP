"""Public entry points: analyze_pdf(path) and analyze_text(text).

CLI:  python -m ingest.pipeline paper.pdf -o paper.json
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from .pdf_reader import Block, Line, read_pdf
from .section_splitter import split_sections
from .sentence_builder import build_sentences


def _package(sections, meta: dict, source: str) -> dict:
    counts: list = []
    sentences = build_sentences(sections, counts)
    keywords: list[str] = []
    for i, sec in enumerate(sections):
        if sec.label == "keywords":
            kw = re.sub(r"\s+", " ", " ".join(sec.paragraphs))
            keywords = [k.strip(" .") for k in re.split(r"[,;\u2022]", kw) if k.strip(" .")]
    return {
        "source": source,
        "title": meta.get("title", ""),
        "keywords": keywords,
        "sections": [
            {"label": s.label, "title": s.title, "subheadings": s.subheadings,
             "n_sentences": counts[i], "text": s.text}
            for i, s in enumerate(sections)
        ],
        "sentences": sentences,
    }


def analyze_pdf(path: str) -> dict:
    blocks, meta = read_pdf(path)
    if sum(len(b.text) for b in blocks) < 300:
        raise ValueError(f"No extractable text in {Path(path).name} - scanned PDF? (OCR is out of scope)")
    return _package(split_sections(blocks), meta, Path(path).name)


def analyze_text(text: str, title: str = "") -> dict:
    """Same pipeline for pasted plain text (paragraphs separated by blank lines)."""
    blocks = []
    for para in re.split(r"\n\s*\n", text):
        lines = [Line(l.strip()) for l in para.splitlines() if l.strip()]
        if lines:
            blocks.append(Block(0, lines))
    return _package(split_sections(blocks), {"title": title}, "pasted_text")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("-o", "--out")
    args = ap.parse_args()
    result = analyze_pdf(args.pdf)
    payload = json.dumps(result, indent=2, ensure_ascii=False)
    if args.out:
        Path(args.out).write_text(payload, encoding="utf-8")
    else:
        print(payload)


if __name__ == "__main__":
    main()
