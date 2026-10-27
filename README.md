# Academic Paper Analyzer - Member 1: ingestion layer

PDF -> clean text -> sections -> sentence list (the shared JSON contract).

## Setup
    pip install -r requirements.txt        # pymupdf, nltk  (punkt_tab downloads automatically)

## Use
    from ingest import analyze_pdf, analyze_text
    result = analyze_pdf("paper.pdf")      # or analyze_text(pasted_text)

    python -m ingest.pipeline paper.pdf -o paper.json
    python test_ingest.py samples/         # prints detected sections for every PDF in a folder

## Output (what Members 2, 3, 4 consume)
    result["sentences"] = [
      {"sentence": "...", "section": "methods", "position": 57},   # contract
      {"sentence": "...", "section": "abstract", "position": 3, "abstract_tag": "objective"}  # optional
    ]
    result["title"], result["keywords"], result["sections"] (label, title, subheadings, n_sentences, text)

Section labels: abstract, introduction, related_work, data, methods, results, discussion,
limitations, conclusion, other.  Dropped from sentences: front_matter, keywords, references, backmatter.
`abstract_tag` (background/objective/method/result/conclusion) appears when a structured abstract
labels its own parts - free weak labels for training.

## What it handles
- single- and two-column layouts, running headers/footers, footnotes, captions, table text
- superscript citation numbers, [1]-style citations, line-break hyphenation
- numbered (1 Introduction), unnumbered (Introduction) and ALL-CAPS headings; inline "Abstract-..." / "Keywords: ..."

## Known limits
- text-based PDFs only (scanned PDFs raise a clear error; OCR not included)
- a heading whose wording is not in the synonym list (section_splitter._PATTERNS) stays inside the previous section
- equations/tables are dropped heuristically, so a few numeric sentences may remain
