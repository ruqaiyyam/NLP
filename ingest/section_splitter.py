"""Blocks -> labelled sections (abstract, introduction, methods, results, ...)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .pdf_reader import KEEP_HYPHEN, Block, Line, join_lines

# label -> heading regex (matched against the heading with numbering removed)
_PATTERNS = [
    ("abstract", r"abstract"),
    ("keywords", r"key ?words?|index terms"),
    ("introduction", r"introduction|background and motivation|motivation"),
    ("related_work", r"related works?|literature (?:review|survey)|review of literature|"
                     r"previous (?:work|studies)|background|state of the art"),
    ("data", r"data(?:sets?)?|data sets?|data (?:collection|description|acquisition|availability|preparation)|"
             r"dataset description|data and preprocessing"),
    ("methods", r"materials? and methods?|methods? and materials?|methods?|methodology|research methodology|"
                r"proposed (?:system|method(?:ology)?|approach|model|framework|architecture|system architecture)|"
                r"system (?:design|architecture|overview|description)|approach|"
                r"experimental (?:setup|set-up|work|design|methodology)|implementation|model|materials|techniques?"),
    ("results", r"results?|experiments?|experimental results?|results? and (?:discussion|analysis)|"
                r"evaluation|findings|performance (?:analysis|evaluation)|experiments? and results?"),
    ("discussion", r"discussions?|analysis|analysis and discussion"),
    ("limitations", r"limitations?|limitations? and future (?:work|scope|directions?)|threats to validity|"
                    r"challenges and limitations"),
    ("conclusion", r"conclusions?|conclusions? and future (?:work|scope|directions?)|concluding remarks|"
                   r"summary|summary and conclusions?|future (?:work|scope|directions?)"),
    ("references", r"references|bibliography|works cited"),
    ("backmatter", r"acknowledge?ments?|funding|declarations?|declaration of (?:conflicting|competing) interests?|"
                   r"conflicts? of interest|ethical approval|ethics(?: statement)?|informed consent|"
                   r"authors?|author contributions?|about the authors?|appendix|appendices|"
                   r"supplementary (?:material|information)|biographies"),
]
_PATTERNS = [(lab, re.compile(p, re.I)) for lab, p in _PATTERNS]
_NUM_PREFIX = re.compile(r"^(?:\d+(?:\.\d+)*\.?\s+|[IVXLC]+\.\s+|[A-H][.)]\s+)")
_INLINE = re.compile(r"^(abstract|key ?words?|index terms)\s*[\u2014\u2013:\-]+\s*(\S.*)$", re.I)

NON_CONTENT = {"front_matter", "keywords", "references", "backmatter"}
_SENT_END = (".", "!", "?", ":", ";", ")", '"', "\u201d")


@dataclass
class Section:
    label: str
    title: str
    paragraphs: list = field(default_factory=list)
    subheadings: list = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n\n".join(self.paragraphs)

    def add(self, piece: str) -> None:
        piece = piece.strip()
        if not piece:
            return
        prev = self.paragraphs[-1] if self.paragraphs else None
        if prev and prev.endswith("-") and piece[0].islower() and len(prev) > 1 and prev[-2].isalpha():
            last = re.search(r"([A-Za-z]+)-$", prev)
            keep = last and last.group(1).lower() in KEEP_HYPHEN
            self.paragraphs[-1] = (prev if keep else prev[:-1]) + piece
            return
        # sentence continued across a column / page break -> glue back together
        if prev and not prev.endswith(_SENT_END) and piece[0].islower():
            self.paragraphs[-1] = prev + " " + piece
        else:
            self.paragraphs.append(piece)


def classify_heading(text: str) -> str | None:
    t = text.strip().rstrip(":.").strip()
    t = _NUM_PREFIX.sub("", t, count=1)
    t = re.sub(r"\s+", " ", t.lower().replace("&", "and")).strip(" :.-\u2013\u2014")
    if not t or len(t) > 60:
        return None
    for label, pat in _PATTERNS:
        if pat.fullmatch(t):
            return label
    return None


def _heading_label(line: Line, idx: int, block: Block) -> str | None:
    label = classify_heading(line.text)
    if label and (len(block.lines) <= 3 or idx == 0 or line.bold):
        return label
    return None


def _is_subheading(block: Block) -> bool:
    """Short, un-punctuated, bold/italic/numbered line(s): '3.1 Output of PPG sensor'."""
    t = block.text.strip()
    if len(block.lines) > 2 or len(t) > 90 or len(t.split()) > 14 or t.endswith((".", "!", "?", ";", ",")):
        return False
    styled = all(l.bold for l in block.lines) or all(l.italic for l in block.lines)
    numbered = bool(re.match(r"^\d+\.\d+(?:\.\d+)*\.?\s+\S", t))
    return styled or numbered


def split_sections(blocks: list[Block]) -> list[Section]:
    sections = [Section("front_matter", "")]

    def start(label: str, title: str) -> None:
        sections.append(Section(label, title))

    for block in blocks:
        if _is_subheading(block) and not any(
                classify_heading(l.text) or _INLINE.match(l.text) for l in block.lines):
            sections[-1].subheadings.append(re.sub(r"\s+", " ", block.text).strip())
            continue
        buf: list[str] = []

        def flush():
            if buf:
                sections[-1].add(join_lines(buf))
                buf.clear()

        for i, line in enumerate(block.lines):
            m = _INLINE.match(line.text)
            if m:  # "Abstract—text..." / "Keywords: a, b, c"
                flush()
                lab = "abstract" if m.group(1).lower().startswith("abs") else "keywords"
                start(lab, m.group(1).title())
                buf.append(m.group(2))
                continue
            label = _heading_label(line, i, block)
            if label:
                flush()
                start(label, _NUM_PREFIX.sub("", line.text, count=1).strip(" :."))
            else:
                buf.append(line.text)
        flush()

    sections = [s for s in sections if s.paragraphs or s.label not in ("front_matter",)]
    if not any(s.label not in NON_CONTENT for s in sections):
        for s in sections:  # no headings found at all -> keep everything
            if s.label == "front_matter":
                s.label = "other"
    return sections
