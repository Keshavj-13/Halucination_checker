import re
from datetime import datetime
from typing import List, Dict, Any, Set, Tuple
from services.voters.base import Voter
from models.schemas import Evidence


class EntityVoter(Voter):
    """Checks entity/date/number agreement with tolerant normalization."""

    ALIASES = {
        "usa": "united states",
        "u.s.": "united states",
        "uk": "united kingdom",
        "u.k.": "united kingdom",
    }

    def _normalize_name(self, token: str) -> str:
        norm = re.sub(r"[^a-z0-9\s]", "", token.lower()).strip()
        return self.ALIASES.get(norm, norm)

    def _extract_names(self, text: str) -> Set[str]:
        raw = re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b", text)
        return {self._normalize_name(x) for x in raw if x}

    def _extract_numbers(self, text: str) -> List[float]:
        nums = []
        for token in re.findall(r"\b\d+(?:,\d{3})*(?:\.\d+)?\b", text):
            nums.append(float(token.replace(",", "")))
        return nums

    def _extract_years(self, text: str) -> Set[int]:
        years = set()
        for y in re.findall(r"\b(19\d{2}|20\d{2})\b", text):
            years.add(int(y))
        return years

    def _number_match_score(self, claim_nums: List[float], evidence_nums: List[float]) -> float:
        if not claim_nums:
            return 0.7
        if not evidence_nums:
            return 0.0

        hits = 0
        for c in claim_nums:
            if any(abs(c - e) <= max(1.0, 0.02 * abs(c)) for e in evidence_nums):
                hits += 1
        return hits / len(claim_nums)

    async def vote(self, claim: str, evidence: List[Evidence]) -> Dict[str, Any]:
        if not evidence:
            return {"status": "Hallucination", "confidence": 0.1, "reasoning": "No evidence available.", "score": 0.1}

        claim_names = self._extract_names(claim)
        claim_years = self._extract_years(claim)
        claim_nums = self._extract_numbers(claim)

        all_evidence_text = " ".join([ev.snippet for ev in evidence])
        evidence_names = self._extract_names(all_evidence_text)
        evidence_years = self._extract_years(all_evidence_text)
        evidence_nums = self._extract_numbers(all_evidence_text)

        name_score = (len(claim_names & evidence_names) / len(claim_names)) if claim_names else 0.7
        year_score = (len(claim_years & evidence_years) / len(claim_years)) if claim_years else 0.7
        number_score = self._number_match_score(claim_nums, evidence_nums)

        total = 0.45 * name_score + 0.30 * year_score + 0.25 * number_score

        if total > 0.78:
            status = "Verified"
        elif total > 0.38:
            status = "Plausible"
        else:
            status = "Hallucination"

        return {
            "status": status,
            "confidence": round(total, 4),
            "reasoning": (
                f"name={name_score:.2f}, date={year_score:.2f}, number={number_score:.2f}"
            ),
            "score": round(total, 4),
        }

entity_voter = EntityVoter()
