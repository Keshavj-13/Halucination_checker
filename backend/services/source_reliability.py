from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlparse


DOMAIN_PRIOR = {
    ".gov": 0.90,
    ".edu": 0.88,
    "reuters.com": 0.85,
    "apnews.com": 0.84,
    "wikipedia.org": 0.72,
}

SPAM_PATTERNS = [r"click here", r"buy now", r"casino", r"viagra"]
SPONSORSHIP_PATTERNS = [
    r"sponsored",
    r"paid partnership",
    r"affiliate",
    r"funded by",
    r"conflict of interest",
    r"advertorial",
]
ADVOCACY_PATTERNS = [
    r"must",
    r"undeniable",
    r"everyone knows",
    r"obviously true",
    r"without question",
]


@dataclass
class SourceReliabilityResult:
    score: float
    explanation: str
    signals: Dict[str, float]


class SourceReliabilityScorer:
    def score_page(
        self,
        url: str,
        title: str,
        text: str,
        claim_text: str,
        headers: Optional[Dict[str, str]] = None,
        cross_source_support: float = 0.0,
    ) -> SourceReliabilityResult:
        headers = headers or {}
        domain_score = self._domain_prior(url)
        quality_score, quality_signals = self._content_quality(text, title)
        freshness_score = self._freshness_score(text, claim_text, headers)
        spam_penalty = self._spam_penalty(text)
        sponsorship_penalty = self._sponsorship_penalty(text)
        advocacy_penalty = self._advocacy_penalty(text)
        bias_penalty = min(max(0.6 * sponsorship_penalty + 0.4 * advocacy_penalty, 0.0), 1.0)
        cross_support = min(max(cross_source_support, 0.0), 1.0)

        base = (
            0.20 * domain_score
            + 0.35 * quality_score
            + 0.20 * freshness_score
            + 0.20 * cross_support
            + 0.05 * (1.0 - spam_penalty)
        )
        score = float(min(max(base - 0.10 * bias_penalty, 0.0), 1.0))

        signals = {
            "domain_prior": domain_score,
            "content_quality": quality_score,
            "freshness": freshness_score,
            "cross_source_support": cross_support,
            "spam_penalty": spam_penalty,
            "sponsorship_penalty": sponsorship_penalty,
            "advocacy_penalty": advocacy_penalty,
            "bias_penalty": bias_penalty,
            "sponsorship_flag": 1.0 if sponsorship_penalty >= 0.2 else 0.0,
            **quality_signals,
        }
        explanation = (
            f"domain={domain_score:.2f}, quality={quality_score:.2f}, freshness={freshness_score:.2f}, "
            f"cross_support={cross_support:.2f}, spam_penalty={spam_penalty:.2f}, "
            f"sponsorship_penalty={sponsorship_penalty:.2f}, advocacy_penalty={advocacy_penalty:.2f}"
        )
        return SourceReliabilityResult(score=score, explanation=explanation, signals=signals)

    def estimate_cross_source_support(self, texts: Iterable[str]) -> List[float]:
        docs = [t or "" for t in texts]
        token_sets = [set(re.findall(r"\w+", t.lower())) for t in docs]
        out: List[float] = []
        for i, a in enumerate(token_sets):
            if not a:
                out.append(0.0)
                continue
            sims = []
            for j, b in enumerate(token_sets):
                if i == j:
                    continue
                union = len(a | b)
                sims.append((len(a & b) / union) if union else 0.0)
            out.append(sum(sims) / len(sims) if sims else 0.0)
        return out

    def _domain_prior(self, url: str) -> float:
        host = urlparse(url).netloc.lower()
        for p, s in DOMAIN_PRIOR.items():
            if host.endswith(p) or host == p:
                return s
        if host.endswith(".org"):
            return 0.64
        if host.endswith(".com"):
            return 0.55
        return 0.50

    def _content_quality(self, text: str, title: str) -> Tuple[float, Dict[str, float]]:
        words = re.findall(r"[A-Za-z0-9]+", text)
        wc = len(words)
        sent = max(1, len(re.findall(r"[.!?]", text)))
        avg_sent = wc / sent
        refs = len(re.findall(r"\b(reference|citation|source|doi|isbn)\b", text.lower()))
        lexical_div = len(set(w.lower() for w in words)) / max(1, wc)
        density = min(wc / 900.0, 1.0)
        cite = min(refs / 6.0, 1.0)
        style = min(max((avg_sent - 8.0) / 20.0, 0.0), 1.0)
        diversity = min(max((lexical_div - 0.2) / 0.5, 0.0), 1.0)
        quality = min(max(0.35 * density + 0.25 * cite + 0.20 * style + 0.20 * diversity, 0.0), 1.0)
        return quality, {
            "text_density": density,
            "citation_signal": cite,
            "factual_style": style,
            "lexical_diversity": diversity,
        }

    def _freshness_score(self, text: str, claim_text: str, headers: Dict[str, str]) -> float:
        dates = []
        lm = headers.get("last-modified")
        if lm:
            try:
                dates.append(parsedate_to_datetime(lm))
            except Exception:
                pass
        for y in re.findall(r"\b(19\d{2}|20\d{2})\b", text):
            try:
                dates.append(datetime(int(y), 1, 1, tzinfo=timezone.utc))
            except ValueError:
                pass
        if not dates:
            return 0.5
        norm = [d if d.tzinfo else d.replace(tzinfo=timezone.utc) for d in dates]
        newest = max(norm)
        age_years = max((datetime.now(timezone.utc) - newest).days / 365.25, 0.0)
        decay = 2.0 if re.search(r"\b(now|current|latest|today|recent|this year)\b", claim_text.lower()) else 6.0
        return float(min(max(pow(2.718281828, -age_years / decay), 0.0), 1.0))

    def _spam_penalty(self, text: str) -> float:
        t = text.lower()
        matches = sum(1 for p in SPAM_PATTERNS if re.search(p, t))
        toks = re.findall(r"[A-Za-z0-9]+", t)
        if not toks:
            return 1.0
        freq = Counter(toks)
        repeat = max(freq.values()) / len(toks)
        return min(0.6 * (matches / max(1, len(SPAM_PATTERNS))) + 0.4 * min(repeat, 1.0), 1.0)

    def _sponsorship_penalty(self, text: str) -> float:
        t = text.lower()
        matches = sum(1 for p in SPONSORSHIP_PATTERNS if re.search(p, t))
        return min(matches / max(1, len(SPONSORSHIP_PATTERNS) * 0.45), 1.0)

    def _advocacy_penalty(self, text: str) -> float:
        t = text.lower()
        matches = sum(1 for p in ADVOCACY_PATTERNS if re.search(p, t))
        caps = len(re.findall(r"\b[A-Z]{4,}\b", text))
        return min(0.7 * (matches / max(1, len(ADVOCACY_PATTERNS) * 0.4)) + 0.3 * min(caps / 12.0, 1.0), 1.0)


source_reliability_scorer = SourceReliabilityScorer()
