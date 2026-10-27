"""PDF -> ordered, cleaned text blocks.

Handles: single/two-column layouts, running headers/footers, footnotes and
small print, captions, table text, superscript citation numbers, hyphenation.
"""
from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field

import pymupdf

BODY_TOL = 1.1  # blocks smaller than (body font - tol) are footnotes/captions/affiliations
KEEP_HYPHEN = {
    "non", "multi", "self", "cross", "semi", "anti", "inter", "intra", "pre",
    "post", "co", "real", "low", "high", "well", "state", "data", "deep",
    "fine", "long", "short", "end", "two", "three", "five", "machine",
}

# whole-line noise: submission dates, journal boilerplate, bare URLs, page numbers
NOISE_LINE = re.compile(
    r"^(?:(?:received|revised|accepted|published|available online|article submitted)\b.{0,80}\d{4}"
    r"|article info|research article|original article|review article"
    r"|copyright\b.*|©.*|https?://\S+|doi:?\s*\S+|e-?issn.*|\d{1,4}|page \d+( of \d+)?)$",
    re.I,
)
CAPTION = re.compile(r"^(?:fig(?:ure)?s?\.?|table|tab\.)\s*[\dIVX]+[a-z]?\s*[.:\-\u2013\u2014]", re.I)
SUBCAPTION = re.compile(r"^[a-h]\)\s+\S")
_NUMLABEL = re.compile(r"^(?:\d+(?:\.\d+)*\.?|[IVX]+\.?)$")
_SUPERSCRIPT_JUNK = re.compile(r"[\d,\s\u2013\u2014\-*\u2020\u2021\u00a7]+")


@dataclass
class Line:
    text: str
    bold: bool = False
    italic: bool = False
    size: float = 0.0


@dataclass
class Block:
    page: int
    lines: list = field(default_factory=list)
    bbox: tuple = (0.0, 0.0, 0.0, 0.0)

    @property
    def text(self) -> str:
        return " ".join(l.text for l in self.lines)

    @property
    def size(self) -> float:
        return max((l.size for l in self.lines), default=0.0)


# --------------------------------------------------------------------------- #
def _norm(t: str) -> str:
    t = unicodedata.normalize("NFKC", t).replace("\u00ad", "")
    return re.sub(r"[ \t\u00a0]+", " ", t).strip()


def _extract_page(page, pno: int) -> list[Block]:
    blocks: list[Block] = []
    for b in page.get_text("dict")["blocks"]:
        if b.get("type") != 0:
            continue
        raw = []
        for l in b["lines"]:
            txt, bolds, itals, sizes = "", [], [], []
            for s in l["spans"]:
                t = s["text"]
                if (s["flags"] & 1) and _SUPERSCRIPT_JUNK.fullmatch(t):
                    continue  # superscript citation / affiliation numbers
                txt += t
                if t.strip():
                    f = s["font"].lower()
                    bolds.append(bool(s["flags"] & 16) or "bold" in f)
                    itals.append(bool(s["flags"] & 2) or "italic" in f or "oblique" in f)
                    sizes.append(s["size"])
            txt = _norm(txt)
            if txt and sizes:
                raw.append([l["bbox"][1], l["bbox"][0], txt, all(bolds), all(itals), max(sizes)])
        # "1" + "Introduction" are separate lines on the same row -> merge
        merged, i = [], 0
        while i < len(raw):
            cur = raw[i]
            if (_NUMLABEL.fullmatch(cur[2]) and i + 1 < len(raw)
                    and abs(raw[i + 1][0] - cur[0]) < 4 and raw[i + 1][1] > cur[1]):
                nxt = raw[i + 1]
                merged.append([cur[0], cur[1], f"{cur[2]} {nxt[2]}", nxt[3], nxt[4], max(cur[5], nxt[5])])
                i += 2
            else:
                merged.append(cur)
                i += 1
        lines = [Line(m[2], m[3], m[4], m[5]) for m in merged if not NOISE_LINE.fullmatch(m[2])]
        if lines:
            blocks.append(Block(pno, lines, tuple(b["bbox"])))
    return blocks


def _is_table_like(b: Block) -> bool:
    txt = b.text
    nonspace = len(re.sub(r"\s", "", txt)) or 1
    digits = sum(c.isdigit() for c in txt) / nonspace
    avg = sum(len(l.text) for l in b.lines) / len(b.lines)
    if len(b.lines) >= 3 and avg < 18:
        return True
    if len(b.lines) >= 2 and digits > 0.3:
        return True
    return digits > 0.5


def _is_caption(b: Block) -> bool:
    t = b.text
    if len(b.lines) == 1 and len(t) < 50 and t[0].islower() and not t.endswith((".", "!", "?")):
        return True  # orphan tail of a wrapped caption
    if len(t) < 250 and CAPTION.match(t):
        return True
    return len(t) < 160 and bool(SUBCAPTION.match(t))


def _order(blocks: list[Block], width: float) -> list[Block]:
    """Reading order. Two-column pages: spanning blocks split the page into
    segments; inside a segment read the left column, then the right."""
    if not blocks:
        return blocks
    mid, tol = width / 2, 10

    def kind(b):
        x0, _, x1, _ = b.bbox
        if x1 <= mid + tol:
            return "L"
        if x0 >= mid - tol:
            return "R"
        return "S"

    big = [b for b in blocks if len(b.text) >= 120]
    left = [b for b in big if kind(b) == "L"]
    right = [b for b in big if kind(b) == "R"]
    side_by_side = any(
        min(l.bbox[3], r.bbox[3]) - max(l.bbox[1], r.bbox[1]) > 40 for l in left for r in right
    )
    if not side_by_side:
        return sorted(blocks, key=lambda b: (round(b.bbox[1]), b.bbox[0]))

    spanners = sorted((b for b in blocks if kind(b) == "S"), key=lambda b: b.bbox[1])
    cols = [b for b in blocks if kind(b) != "S"]
    ys = [s.bbox[1] for s in spanners]

    def seg(b):
        yc = (b.bbox[1] + b.bbox[3]) / 2
        return sum(1 for y in ys if y < yc)

    out: list[Block] = []
    for i in range(len(spanners) + 1):
        inside = [b for b in cols if seg(b) == i]
        out += sorted((b for b in inside if kind(b) == "L"), key=lambda b: b.bbox[1])
        out += sorted((b for b in inside if kind(b) == "R"), key=lambda b: b.bbox[1])
        if i < len(spanners):
            out.append(spanners[i])
    return out


def _guess_title(page_blocks: list[Block]) -> str:
    if not page_blocks:
        return ""
    top = max(b.size for b in page_blocks)
    parts = [b for b in page_blocks if b.size >= top - 0.3]
    parts.sort(key=lambda b: (b.bbox[1], b.bbox[0]))
    return re.sub(r"\s+", " ", " ".join(b.text for b in parts)).strip()


def _keep_hyphen(first: str, head: str, vocab: set) -> bool:
    """Is the hyphen at a line break part of a real compound (hemoglobin-dependent)?"""
    first, head = first.lower(), head.lower()
    if first in KEEP_HYPHEN:
        return True
    if first + head in vocab:
        return False
    return len(first) >= 3 and len(head) >= 3 and first in vocab and head in vocab


def _dehyphenate(blocks: list[Block]) -> None:
    """Repair words split across lines, using the paper's own vocabulary."""
    vocab: set = set()  # whole words only: skip the fragments on both sides of a line-break hyphen
    for b in blocks:
        carry = False
        for l in b.lines:
            t = l.text.lower()
            if carry:
                t = re.sub(r"^[a-z]+", "", t)
            carry = t.endswith("-")
            if carry:
                t = re.sub(r"[a-z]*-$", "", t)
            vocab.update(re.findall(r"[a-z]{3,}", t))
    for b in blocks:
        for i in range(len(b.lines) - 1):
            cur, nxt = b.lines[i], b.lines[i + 1]
            m = re.search(r"([A-Za-z]+)-$", cur.text)
            h = re.match(r"([a-z]+)(.*)$", nxt.text)
            if not (m and h):
                continue
            if _keep_hyphen(m.group(1), h.group(1), vocab):
                cur.text = cur.text + h.group(1)
            else:
                cur.text = cur.text[:-1] + h.group(1)
            nxt.text = h.group(2).lstrip()
        b.lines = [l for l in b.lines if l.text]


def join_lines(lines: list[str]) -> str:
    """Join wrapped lines (hyphenation is already repaired by _dehyphenate)."""
    out = ""
    for ln in lines:
        t = ln.strip()
        if not t:
            continue
        if not out:
            out = t
        elif out.endswith("-") and t[0].isupper() and len(out) > 1 and out[-2].isalpha():
            out += t  # "Plethysmo-" + "Graphic": keep the hyphen, no space
        else:
            out += " " + t
    return out


# --------------------------------------------------------------------------- #
def read_pdf(path: str) -> tuple[list[Block], dict]:
    """Return (ordered clean blocks, meta) for a text-based PDF."""
    doc = pymupdf.open(path)
    pages = [_extract_page(p, i) for i, p in enumerate(doc)]
    widths = [p.rect.width for p in doc]
    n = len(pages)
    meta = {"pages": n, "title": _guess_title(pages[0]) if pages else ""}

    # body font size = most common size, weighted by characters
    cnt: Counter = Counter()
    for pg in pages:
        for b in pg:
            for l in b.lines:
                cnt[round(l.size, 1)] += len(l.text)
    body = cnt.most_common(1)[0][0] if cnt else 10.0
    meta["body_font_size"] = body

    # running headers / footers: short blocks whose digit-normalised text repeats across pages
    seen: dict[str, set] = {}
    for pg in pages:
        for b in pg:
            if len(b.lines) <= 3 and len(b.text) <= 160:
                key = re.sub(r"\d+", "#", b.text.lower())
                seen.setdefault(key, set()).add(b.page)
    need = max(2, math.ceil(0.3 * n))
    repeated = {k for k, v in seen.items() if len(v) >= need}

    ordered: list[Block] = []
    for pg, w in zip(pages, widths):
        keep = []
        for b in pg:
            if len(b.lines) <= 3 and re.sub(r"\d+", "#", b.text.lower()) in repeated:
                continue
            if b.size < body - BODY_TOL:
                continue
            if _is_caption(b) or _is_table_like(b):
                continue
            keep.append(b)
        ordered += _order(keep, w)
    _dehyphenate(ordered)
    return ordered, meta
