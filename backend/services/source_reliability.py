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
    "who.int": 0.91,
    "cdc.gov": 0.90,
    "nih.gov": 0.90,
    "nasa.gov": 0.90,
    "noaa.gov": 0.89,
    "ec.europa.eu": 0.88,
    "oecd.org": 0.86,
    "worldbank.org": 0.86,
    "imf.org": 0.86,
    "nature.com": 0.87,
    "science.org": 0.87,
    "thelancet.com": 0.86,
    "nejm.org": 0.86,
    "bmj.com": 0.85,
    "arxiv.org": 0.78,
    "cochranelibrary.com": 0.88,
    "reuters.com": 0.85,
    "apnews.com": 0.84,
    "bbc.com": 0.82,
    "ft.com": 0.81,
    "economist.com": 0.80,
    "wsj.com": 0.80,
    "nytimes.com": 0.80,
    "wikipedia.org": 0.72,
    "stanford.edu": 0.89,
    "mit.edu": 0.89,
    "harvard.edu": 0.89,
    "ox.ac.uk": 0.89,
    "cam.ac.uk": 0.89,
    "iea.org": 0.85,
    "un.org": 0.88,
    "europa.eu": 0.88,
    "fda.gov": 0.90,
    "ema.europa.eu": 0.89,
    "nber.org": 0.84,
    "rand.org": 0.82,
    "brookings.edu": 0.80,
    "pewresearch.org": 0.83,
    "ourworldindata.org": 0.83,
    "census.gov": 0.90,
    "bls.gov": 0.89,
    "bea.gov": 0.89,
    "sec.gov": 0.89,
    "data.gov": 0.88,
    "ipcc.ch": 0.88,
    "usda.gov": 0.88,
    "usgs.gov": 0.88,
    "esa.int": 0.87,
    "jpl.nasa.gov": 0.90,
}

LOW_TRUST_DOMAIN_PENALTY = {
    "medium.com": 0.08,
    "substack.com": 0.08,
    "quora.com": 0.14,
    "pinterest.com": 0.14,
    "reddit.com": 0.12,
    "tiktok.com": 0.20,
    "instagram.com": 0.20,
    "facebook.com": 0.18,
    "x.com": 0.18,
    "twitter.com": 0.18,
    "buzzfeed.com": 0.12,
    "ifunny.co": 0.22,
    "9gag.com": 0.22,
    "imgur.com": 0.20,
    "change.org": 0.12,
    "wattpad.com": 0.22,
    "blogspot.com": 0.12,
    "wordpress.com": 0.10,
    "tumblr.com": 0.14,
    "telegram.me": 0.20,
    "discord.com": 0.16,
    "patreon.com": 0.10,
    "rumble.com": 0.18,
    "odyssee.com": 0.18,
}

SPAM_PATTERNS = [
    r"click here",
    r"buy now",
    r"limited time",
    r"act now",
    r"casino",
    r"viagra",
    r"free money",
    r"miracle cure",
    r"guaranteed",
    r"risk[- ]free",
    r"double your",
    r"make money fast",
    r"work from home and earn",
    r"lowest price",
    r"best deal",
    r"exclusive offer",
    r"order now",
    r"subscribe now",
    r"instant results",
    r"no effort",
    r"one weird trick",
    r"cure all",
    r"detox",
    r"lose weight fast",
    r"before and after",
    r"sweepstakes",
    r"lottery",
    r"jackpot",
    r"crypto giveaway",
    r"airdrop",
    r"pump and dump",
    r"100 percent guaranteed",
    r"money back",
    r"urgent action required",
    r"act immediately",
    r"limited stock",
    r"don.t miss out",
    r"shop now",
    r"claim your prize",
    r"free trial",
    r"cancel anytime",
    r"sponsored link",
    r"recommended for you",
    r"must read",
    r"breakthrough offer",
    r"secret formula",
    r"miracle",
    r"instant cure",
]
SPONSORSHIP_PATTERNS = [
    r"sponsored",
    r"paid partnership",
    r"affiliate",
    r"funded by",
    r"conflict of interest",
    r"advertorial",
    r"partner content",
    r"promoted",
    r"sponsor(ed)? by",
    r"paid post",
    r"brand partner",
    r"brand partnership",
    r"in collaboration with",
    r"supported by",
    r"made possible by",
    r"presented by",
    r"brought to you by",
    r"this content is sponsored",
    r"sponsorship disclosure",
    r"compensated",
    r"commission",
    r"affiliate disclosure",
    r"contains affiliate links",
    r"may earn a commission",
    r"paid endorsement",
    r"promotional content",
    r"native advertising",
    r"advertisement",
    r"ad "
]
ADVOCACY_PATTERNS = [
    r"must",
    r"undeniable",
    r"everyone knows",
    r"obviously true",
    r"without question",
    r"shocking truth",
    r"they don't want you to know",
    r"wake up",
    r"always",
    r"never",
    r"prove(s|d)? once and for all",
    r"everyone must",
    r"no one can deny",
    r"undisputed",
    r"absolutely",
    r"certainly",
    r"clearly",
    r"plainly",
    r"obvious",
    r"beyond doubt",
    r"guarantees",
    r"totally",
    r"completely",
    r"definitely",
    r"never ever",
    r"always true",
    r"the only truth",
    r"final proof",
    r"ultimate proof",
    r"mainstream lies",
    r"cover[- ]up",
    r"massive conspiracy",
    r"you.ve been lied to",
    r"no debate",
    r"case closed",
    r"obviously false",
    r"obviously correct",
    r"no question",
    r"undeniably",
    r"irrefutable",
]

FACTUAL_VIBE_PATTERNS = [
    r"according to",
    r"data show(s|ed)?",
    r"measured",
    r"methodology",
    r"sample size",
    r"confidence interval",
    r"peer[- ]review(ed)?",
    r"official statistics",
    r"published",
    r"journal",
    r"peer review",
    r"meta[- ]analysis",
    r"systematic review",
    r"method",
    r"methods",
    r"results",
    r"limitations",
    r"confidence level",
    r"p[- ]value",
    r"standard deviation",
    r"control group",
    r"randomized",
    r"double blind",
    r"cohort",
    r"longitudinal",
    r"dataset",
    r"appendix",
    r"supplementary",
    r"official report",
    r"regulatory filing",
    r"public records",
    r"cited",
    r"references",
    r"bibliography",
    r"doi",
    r"isbn",
    r"transparent methodology",
    r"replication",
    r"reproducible",
    r"independent verification",
    r"cross[- ]validated",
    r"statistical significance",
    r"data source",
    r"open data",
    r"raw data",
    r"technical report",
    r"white paper",
    r"supplemental material",
]

HYPE_VIBE_PATTERNS = [
    r"secret",
    r"mind[- ]blowing",
    r"explosive",
    r"unbelievable",
    r"game[- ]changing",
    r"instantly",
    r"viral",
    r"you won.t believe",
    r"jaw[- ]dropping",
    r"insane",
    r"crazy",
    r"epic",
    r"wild",
    r"destroyed",
    r"obliterated",
    r"exposed",
    r"truth bomb",
    r"this changes everything",
    r"must watch",
    r"must read",
    r"ultimate guide",
    r"guaranteed success",
    r"instant hack",
    r"life[- ]changing",
    r"blow your mind",
    r"no one tells you",
    r"hidden secret",
    r"shocking",
    r"unreal",
    r"insider trick",
    r"clickbait",
    r"meltdown",
    r"panic",
    r"fear",
    r"do this now",
    r"urgent",
    r"catastrophic",
    r"apocalyptic",
    r"sensational",
    r"bombshell",
    r"controversial",
    r"outrage",
    r"rage",
    r"fury",
    r"tears",
    r"wrecked",
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
        low_trust_penalty = self._low_trust_domain_penalty(url)
        quality_score, quality_signals = self._content_quality(text, title)
        freshness_score = self._freshness_score(text, claim_text, headers)
        spam_penalty = self._spam_penalty(text)
        sponsorship_penalty = self._sponsorship_penalty(text)
        advocacy_penalty = self._advocacy_penalty(text)
        vibe_bonus, vibe_penalty = self._vibe_scores(text)
        bias_penalty = min(max(0.6 * sponsorship_penalty + 0.4 * advocacy_penalty, 0.0), 1.0)
        cross_support = min(max(cross_source_support, 0.0), 1.0)

        base = (
            0.22 * domain_score
            + 0.35 * quality_score
            + 0.20 * freshness_score
            + 0.20 * cross_support
            + 0.03 * (1.0 - spam_penalty)
        )
        score = float(min(max(base + 0.05 * vibe_bonus - 0.08 * vibe_penalty - 0.10 * bias_penalty - 0.08 * low_trust_penalty, 0.0), 1.0))

        signals = {
            "domain_prior": domain_score,
            "low_trust_domain_penalty": low_trust_penalty,
            "content_quality": quality_score,
            "freshness": freshness_score,
            "cross_source_support": cross_support,
            "spam_penalty": spam_penalty,
            "sponsorship_penalty": sponsorship_penalty,
            "advocacy_penalty": advocacy_penalty,
            "factual_vibe_bonus": vibe_bonus,
            "hype_vibe_penalty": vibe_penalty,
            "bias_penalty": bias_penalty,
            "sponsorship_flag": 1.0 if sponsorship_penalty >= 0.2 else 0.0,
            **quality_signals,
        }
        explanation = (
            f"domain={domain_score:.2f}, quality={quality_score:.2f}, freshness={freshness_score:.2f}, "
            f"cross_support={cross_support:.2f}, spam_penalty={spam_penalty:.2f}, low_trust_domain_penalty={low_trust_penalty:.2f}, "
            f"sponsorship_penalty={sponsorship_penalty:.2f}, advocacy_penalty={advocacy_penalty:.2f}, "
            f"factual_vibe_bonus={vibe_bonus:.2f}, hype_vibe_penalty={vibe_penalty:.2f}"
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

    def _low_trust_domain_penalty(self, url: str) -> float:
        host = urlparse(url).netloc.lower()
        for p, pen in LOW_TRUST_DOMAIN_PENALTY.items():
            if host.endswith(p) or host == p:
                return float(pen)
        return 0.0

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

    def _vibe_scores(self, text: str) -> Tuple[float, float]:
        t = text.lower()
        factual_hits = sum(1 for p in FACTUAL_VIBE_PATTERNS if re.search(p, t))
        hype_hits = sum(1 for p in HYPE_VIBE_PATTERNS if re.search(p, t))
        bonus = min(factual_hits / max(1, len(FACTUAL_VIBE_PATTERNS) * 0.35), 1.0)
        penalty = min(hype_hits / max(1, len(HYPE_VIBE_PATTERNS) * 0.35), 1.0)
        return bonus, penalty


source_reliability_scorer = SourceReliabilityScorer()
