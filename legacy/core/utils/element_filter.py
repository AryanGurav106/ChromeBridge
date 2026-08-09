"""Task-conditioned element filtering — a deterministic, LLM-free pre-filter.

Why this (and not embeddings)
-----------------------------
The repo shipped ``semantic_dom_filter.py`` (GPT-4o-mini keyword extraction ->
text-embedding-3-small -> cosine top-k). The literature is decisive that *dense
embeddings over DOM/AX text fail*: LineRetriever (arXiv:2507.00210) measured
dense retrieval at 7.8% on WebArena / 19.4% on WorkArena — worse than naive
truncation — because element text is short, repetitive, and ambiguous, so cosine
similarity to the goal does not capture *which element advances the task*.

Prune4Web (arXiv:2511.21398) gets grounding 46.8% -> 88.3% with a much simpler
idea: score *interactive-only* elements with a **tiered lexical/fuzzy matcher**
(match quality: exact > phrase > word > fuzzy; attribute trust: visible-text >
trusted-attrs > other-attrs), keep a generous top-K (it uses 20, with
Recall@20 > 95%). The decision LLM then grounds over that shortlist.

This module implements that tiered scorer deterministically — no extra LLM call,
sub-millisecond — over the flat records from ``dom_serializer.flatten_tree``.
It is the cheap Stage-1 of the grounding cascade. Recall is protected by:
  * a generous default ``top_k`` (30),
  * an interactivity/visibility prior so on-screen actionable elements never
    rank last purely for lacking matching text,
  * a fallback that returns all interactive elements when the query matches
    almost nothing (so the grounder is never starved of candidates).
"""

import re
from difflib import SequenceMatcher
from typing import Any, Optional

from core.utils.dom_serializer import is_interactive

# Words that carry no targeting signal — dropped from the query.
_STOPWORDS = {
    "the", "a", "an", "to", "of", "in", "on", "for", "and", "or", "with", "into",
    "click", "type", "enter", "select", "find", "look", "page", "button", "link",
    "field", "element", "please", "current", "step", "user", "looking", "want",
    "this", "that", "is", "are", "be", "you", "your", "it", "at", "by", "from",
    "get", "go", "open", "fill", "input", "box", "then", "if", "as", "use",
}

# Attribute-trust weights (Prune4Web's β tiers): visible text/name is most
# trustworthy, ARIA/placeholder next, structural attrs (class/testid/role) least.
_TIER_WEIGHTS = {
    "visible": 1.0,    # label / name / visible text
    "trusted": 0.6,    # aria-label, placeholder
    "other": 0.3,      # class, testid, role, type, tag
}

_PHRASE_RE = re.compile(r"['\"]([^'\"]{2,60})['\"]")
_WORD_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    return [w for w in _WORD_RE.findall((text or "").lower()) if w not in _STOPWORDS and len(w) > 1]


def extract_query(*parts: str) -> dict[str, Any]:
    """Derive targeting signal from the step/request text.

    Returns quoted phrases (high-value exact targets) and a de-duplicated set of
    content words. Quoted phrases mirror Prune4Web's "primary targets".
    """
    blob = " ".join(p for p in parts if p)
    phrases = [m.strip().lower() for m in _PHRASE_RE.findall(blob)]
    words = _tokenize(blob)
    # keep order-preserving unique words
    seen: set[str] = set()
    uniq_words = [w for w in words if not (w in seen or seen.add(w))]
    return {"phrases": phrases, "words": uniq_words}


def _haystacks(r: dict[str, Any]) -> dict[str, str]:
    """Build the per-trust-tier searchable text for an element record."""
    visible = " ".join(str(r.get(k) or "") for k in ("label", "name")).lower()
    trusted = " ".join(str(r.get(k) or "") for k in ("aria_label", "placeholder")).lower()
    other = " ".join(
        str(r.get(k) or "") for k in ("class", "testid", "role", "type", "tag")
    ).lower()
    return {"visible": visible, "trusted": trusted, "other": other}


def _tier_score(query: dict[str, Any], hay: dict[str, str]) -> float:
    """Tiered match score for one element across its trust tiers."""
    phrases = query["phrases"]
    words = query["words"]
    score = 0.0

    for tier, text in hay.items():
        if not text:
            continue
        w = _TIER_WEIGHTS[tier]
        toks = set(_WORD_RE.findall(text))

        # exact phrase containment — strongest signal
        for ph in phrases:
            if ph and ph in text:
                score += 3.0 * w

        # whole-word matches
        matched = 0
        for word in words:
            if word in toks:
                matched += 1
        if words:
            score += w * (matched / len(words)) * 2.0

        # fuzzy fallback only on the visible tier (catch minor vari/abbreviations),
        # cheap and bounded — avoids over-rewarding noisy class strings.
        if tier == "visible" and words and matched == 0 and text:
            best = max(
                (SequenceMatcher(None, word, tok).ratio()
                 for word in words for tok in toks),
                default=0.0,
            )
            if best >= 0.82:
                score += w * best
    return score


def _prior(r: dict[str, Any]) -> float:
    """Small structural prior: prefer on-screen, actionable, un-occluded elements."""
    p = 0.0
    if is_interactive(r):
        p += 0.4
    if r.get("in_viewport", True):
        p += 0.2
    if r.get("clickable_at_point") is True:
        p += 0.2
    if r.get("clickable_at_point") is False:
        p -= 0.3  # covered by an overlay
    return p


def filter_elements(
    elements: list[dict[str, Any]],
    *query_parts: str,
    top_k: int = 30,
    interactive_only: bool = True,
) -> list[dict[str, Any]]:
    """Rank ``elements`` against the task text and return the top-K candidates.

    Each returned record gains a ``_score`` key (for debugging / the grounder).
    The order is most-relevant-first. Recall is protected: if scoring yields
    essentially nothing, we fall back to all interactive elements (capped).
    """
    if not elements:
        return []

    pool = [e for e in elements if is_interactive(e)] if interactive_only else list(elements)
    if not pool:
        pool = list(elements)

    query = extract_query(*query_parts)
    have_query = bool(query["phrases"] or query["words"])

    scored: list[tuple[float, float, dict[str, Any]]] = []
    for r in pool:
        text_score = _tier_score(query, _haystacks(r)) if have_query else 0.0
        prior = _prior(r)
        total = text_score + prior
        r2 = dict(r)
        r2["_score"] = round(total, 3)
        # reading-order tiebreak so equal-score elements come out top-to-bottom
        box = r.get("box") or {}
        order = (box.get("y") or 0) * 10000 + (box.get("x") or 0)
        scored.append((total, -order, r2))

    # If a real query matched almost nothing (max text contribution ~0), the
    # ranking is just priors — keep it, but it effectively becomes "all
    # interactive, on-screen first", which is the safe high-recall fallback.
    scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return [r for _, _, r in scored[:top_k]]
