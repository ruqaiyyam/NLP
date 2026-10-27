"""Sections -> sentence list in the team's shared JSON contract.

Each item: {"sentence": str, "section": str, "position": int}
(+ optional "abstract_tag" when a structured abstract names the part).
"""
from __future__ import annotations

import re

import nltk

from .section_splitter import NON_CONTENT, Section

_ABBREV = {"et al", "al", "fig", "figs", "eq", "eqs", "e.g", "i.e", "vs", "approx",
           "no", "dr", "prof", "ref", "refs", "sec", "cf", "etc", "ca", "resp", "ph.d", "m.tech"}


def _load_tokenizer():
    try:
        from nltk.tokenize import PunktTokenizer  # nltk >= 3.9
        try:
            tok = PunktTokenizer("english")
        except LookupError:
            nltk.download("punkt_tab", quiet=True)
            tok = PunktTokenizer("english")
    except ImportError:  # older nltk
        try:
            tok = nltk.data.load("tokenizers/punkt/english.pickle")
        except LookupError:
            nltk.download("punkt", quiet=True)
            tok = nltk.data.load("tokenizers/punkt/english.pickle")
    tok._params.abbrev_types.update(_ABBREV)
    return tok


_TOK = _load_tokenizer()
_CITATION = re.compile(r"\s*\[\s*\d+(?:\s*[,\u2013\-]\s*\d+)*\s*\]")
_ABS_TAG = re.compile(
    r"^(background|purpose|objectives?|aims?|introduction|methods?|methodology|results?|conclusions?)\s*:\s+", re.I)
_TAG_MAP = {"background": "background", "introduction": "background", "purpose": "objective",
            "objective": "objective", "objectives": "objective", "aim": "objective", "aims": "objective",
            "method": "method", "methods": "method", "methodology": "method",
            "result": "result", "results": "result", "conclusion": "conclusion", "conclusions": "conclusion"}


def _is_junk(s: str) -> bool:
    words = re.findall(r"[A-Za-z]{2,}", s)
    if len(words) < 5:
        return True
    letters = sum(c.isalpha() for c in s)
    if letters / max(1, len(s.replace(" ", ""))) < 0.6:
        return True
    if "=" in s and sum(len(w) >= 4 for w in words) < 5:  # equation residue
        return True
    return False


def _clean(s: str) -> str:
    prev = None
    while prev != s:
        prev, s = s, _CITATION.sub("", s)
    s = re.sub(r"\s+([,.;:)])", r"\1", s)
    return re.sub(r"\s+", " ", s).strip()


_BULLET = re.compile(r"[\u2022\u25aa\u25e6\u25cf\u00b7]")


def build_sentences(sections: list[Section], counts: list | None = None) -> list[dict]:
    """counts (optional, same length as sections) is filled with sentences kept per section."""
    out: list[dict] = []
    for si, sec in enumerate(sections):
        if counts is not None:
            counts.append(0)
        if sec.label in NON_CONTENT:
            continue
        text = " ".join(sec.paragraphs)
        text = re.sub(r"[.!?:;]?\s*" + _BULLET.pattern + r"\s*", ". ", text)  # bullet = sentence break
        text = _BULLET.sub("", re.sub(r"\s+", " ", text))
        for raw in _TOK.tokenize(text):
            s = _clean(raw)
            tag = None
            if sec.label == "abstract":
                m = _ABS_TAG.match(s)
                if m:
                    tag, s = _TAG_MAP[m.group(1).lower()], s[m.end():]
            if _is_junk(s):
                continue
            item = {"sentence": s, "section": sec.label, "position": len(out)}
            if tag:
                item["abstract_tag"] = tag
            out.append(item)
            if counts is not None:
                counts[si] += 1
    return out
