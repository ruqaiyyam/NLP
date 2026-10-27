"""Run the ingestion pipeline on PDFs and print what was detected.

Usage: python test_ingest.py [pdf_or_folder ...]   (default: ./samples)
Writes <name>.json next to each PDF's output folder (./outputs).
"""
import json
import sys
from pathlib import Path

from ingest import analyze_pdf


def main(args):
    targets = [Path(a) for a in args] or [Path("samples")]
    pdfs = []
    for t in targets:
        pdfs += sorted(t.glob("*.pdf")) if t.is_dir() else [t]
    Path("outputs").mkdir(exist_ok=True)
    for pdf in pdfs:
        res = analyze_pdf(str(pdf))
        Path("outputs", pdf.stem + ".json").write_text(
            json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
        print("=" * 78)
        print(pdf.name)
        print("TITLE   :", res["title"])
        print("KEYWORDS:", res["keywords"])
        print(f"SENTENCES: {len(res['sentences'])}")
        by = {}
        for s in res["sentences"]:
            by[s["section"]] = by.get(s["section"], 0) + 1
        print("SECTIONS:")
        for sec in res["sections"]:
            n = by.get(sec["label"], 0) if sec["label"] not in ("keywords", "references", "backmatter") else "-"
            print(f"  [{sec['label']:<13}] {sec['title'][:42]:<42} sents={sec["n_sentences"]:>3}  subheads={len(sec["subheadings"])}")
        print("COUNT BY LABEL:", by)


if __name__ == "__main__":
    main(sys.argv[1:])
