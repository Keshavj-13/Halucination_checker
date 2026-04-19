from __future__ import annotations

import re
from typing import Any, Dict, List

import joblib
import numpy as np
from scipy.sparse import csr_matrix, hstack

from models.schemas import Evidence
from services.config import CONSISTENCY_MODEL_PATH
from services.voters.base import Voter


class ConsistencyVoter(Voter):
    def __init__(self):
        self.model = None
        self.feature_set = "word_dense"
        self.vectorizer = None
        self.char_vectorizer = None
        self.scaler = None
        self.class_labels = ["refuted", "supported", "insufficient"]
        self.ensemble_members: list[dict] = []

        if CONSISTENCY_MODEL_PATH.exists():
            artifact = joblib.load(CONSISTENCY_MODEL_PATH)
            if isinstance(artifact, dict):
                self.model = artifact.get("model")
                self.feature_set = artifact.get("feature_set", "word_dense")
                self.vectorizer = artifact.get("vectorizer")
                self.char_vectorizer = artifact.get("char_vectorizer")
                self.scaler = artifact.get("scaler")
                self.class_labels = [str(c).lower() for c in artifact.get("class_labels", self.class_labels)]
                self.ensemble_members = artifact.get("ensemble_members", []) or []
            else:
                self.model = artifact

    def _features(self, claim: str, evidence: Evidence) -> np.ndarray:
        claim_tokens = set(re.findall(r"\w+", claim.lower()))
        ev_tokens = set(re.findall(r"\w+", evidence.snippet.lower()))
        overlap = len(claim_tokens & ev_tokens) / max(1, len(claim_tokens))

        claim_numbers = [float(x) for x in re.findall(r"\b\d+(?:\.\d+)?\b", claim)]
        ev_numbers = [float(x) for x in re.findall(r"\b\d+(?:\.\d+)?\b", evidence.snippet)]
        if claim_numbers:
            number_agreement = sum(
                1 for c in claim_numbers if any(abs(c - e) <= max(1.0, abs(c) * 0.02) for e in ev_numbers)
            ) / len(claim_numbers)
        else:
            number_agreement = 0.7

        claim_years = set(re.findall(r"\b(19\d{2}|20\d{2})\b", claim))
        ev_years = set(re.findall(r"\b(19\d{2}|20\d{2})\b", evidence.snippet))
        date_agreement = len(claim_years & ev_years) / max(1, len(claim_years)) if claim_years else 0.7

        return np.array(
            [
                overlap,
                number_agreement,
                date_agreement,
                evidence.reliability_score,
                min(len(evidence.snippet.split()) / 220.0, 1.0),
            ],
            dtype=np.float32,
        )

    def _predict_proba_compat(self, model, feature_matrix) -> tuple[np.ndarray, list[str]]:
        if hasattr(model, "predict_proba"):
            return model.predict_proba(feature_matrix), [str(c).lower() for c in model.classes_]
        if hasattr(model, "decision_function"):
            scores = np.asarray(model.decision_function(feature_matrix))
            classes = [str(c).lower() for c in model.classes_]
            if scores.ndim == 1:
                p1 = 1.0 / (1.0 + np.exp(-scores))
                probs = np.column_stack([1.0 - p1, p1])
            else:
                shifted = scores - np.max(scores, axis=1, keepdims=True)
                exp_scores = np.exp(shifted)
                probs = exp_scores / np.clip(np.sum(exp_scores, axis=1, keepdims=True), 1e-8, None)
            return probs, classes
        preds = model.predict(feature_matrix)
        classes = sorted({str(p).lower() for p in preds})
        probs = np.zeros((len(preds), len(classes)), dtype=np.float32)
        c2i = {c: i for i, c in enumerate(classes)}
        for i, p in enumerate(preds):
            probs[i, c2i[str(p).lower()]] = 1.0
        return probs, classes

    def _align_probs(self, probs: np.ndarray, src_classes: list[str], dst_classes: list[str]) -> np.ndarray:
        aligned = np.zeros((probs.shape[0], len(dst_classes)), dtype=np.float32)
        for src_i, c in enumerate(src_classes):
            if c in dst_classes:
                aligned[:, dst_classes.index(c)] = probs[:, src_i]
        sums = aligned.sum(axis=1, keepdims=True)
        sums = np.where(sums <= 1e-8, 1.0, sums)
        return aligned / sums

    def _build_feature_matrix(
        self,
        claim: str,
        evidence: List[Evidence],
        dense: np.ndarray,
        feature_set: str,
        vectorizer,
        char_vectorizer,
        scaler,
    ):
        if feature_set == "dense" and scaler is not None:
            return scaler.transform(dense)
        if vectorizer is not None and scaler is not None:
            text_rows = [f"{claim} [SEP] {ev.snippet}" for ev in evidence]
            text_sparse = vectorizer.transform(text_rows)
            dense_scaled = scaler.transform(dense)
            parts = [text_sparse]
            if feature_set == "word_char_dense" and char_vectorizer is not None:
                parts.append(char_vectorizer.transform(text_rows))
            parts.append(csr_matrix(dense_scaled))
            return hstack(parts)
        return dense

    def _fallback_score(self, claim: str, evidence: List[Evidence]) -> Dict[str, Any]:
        if not evidence:
            return {"status": "Hallucination", "confidence": 0.1, "reasoning": "No evidence available.", "score": 0.1}
        scores = []
        for ev in evidence:
            f = self._features(claim, ev)
            s = 0.4 * f[0] + 0.2 * f[1] + 0.2 * f[2] + 0.2 * f[3]
            scores.append((float(s), ev))
        best_score, _ = max(scores, key=lambda x: x[0])
        if best_score >= 0.68:
            status = "Verified"
        elif best_score >= 0.38:
            status = "Plausible"
        else:
            status = "Hallucination"
        return {
            "status": status,
            "confidence": round(best_score, 4),
            "reasoning": "Fallback lightweight consistency features.",
            "score": round(best_score, 4),
        }

    async def vote(self, claim: str, evidence: List[Evidence]) -> Dict[str, Any]:
        if not self.model and not self.ensemble_members:
            return self._fallback_score(claim, evidence)
        if not evidence:
            return {"status": "Hallucination", "confidence": 0.1, "reasoning": "No evidence available.", "score": 0.1}

        dense = np.vstack([self._features(claim, ev) for ev in evidence])

        if self.ensemble_members:
            dst = self.class_labels
            agg = np.zeros((len(evidence), len(dst)), dtype=np.float32)
            total = 0.0
            for m in self.ensemble_members:
                mm = m.get("model")
                if mm is None:
                    continue
                fm = self._build_feature_matrix(
                    claim,
                    evidence,
                    dense,
                    m.get("feature_set", "word_dense"),
                    m.get("vectorizer"),
                    m.get("char_vectorizer"),
                    m.get("scaler"),
                )
                raw, cls = self._predict_proba_compat(mm, fm)
                probs = self._align_probs(raw, cls, dst)
                w = float(m.get("weight", 1.0))
                agg += w * probs
                total += w
            if total <= 0:
                return self._fallback_score(claim, evidence)
            probs = agg / total
            classes = dst
        else:
            fm = self._build_feature_matrix(
                claim,
                evidence,
                dense,
                self.feature_set,
                self.vectorizer,
                self.char_vectorizer,
                self.scaler,
            )
            probs, classes = self._predict_proba_compat(self.model, fm)

        support_idx = classes.index("supported") if "supported" in classes else 0
        refute_idx = classes.index("refuted") if "refuted" in classes else min(1, probs.shape[1] - 1)
        uncertain_idx = classes.index("insufficient") if "insufficient" in classes else min(2, probs.shape[1] - 1)

        weights = []
        support_vals = []
        refute_vals = []
        uncertain_vals = []
        for i, ev in enumerate(evidence):
            rel = max(0.05, float(ev.reliability_score))
            stance = (ev.stance or "mention").lower()
            if stance in {"support"}:
                stance_w = 1.15
            elif stance in {"refute"}:
                stance_w = 1.15
            elif stance in {"neutral"}:
                stance_w = 0.70
            elif stance in {"quotation", "reported_belief", "mention"}:
                stance_w = 0.35
            else:
                stance_w = 0.55
            w = rel * stance_w * (1.0 - min(max(float(ev.bias_penalty), 0.0), 1.0) * 0.35)
            weights.append(w)
            support_vals.append(float(probs[i, support_idx]))
            refute_vals.append(float(probs[i, refute_idx]))
            uncertain_vals.append(float(probs[i, uncertain_idx]))

        wsum = max(1e-8, sum(weights))
        support_conf = float(sum(v * w for v, w in zip(support_vals, weights)) / wsum)
        refute_conf = float(sum(v * w for v, w in zip(refute_vals, weights)) / wsum)
        uncertain_conf = float(sum(v * w for v, w in zip(uncertain_vals, weights)) / wsum)

        if support_conf >= max(refute_conf, uncertain_conf) and support_conf >= 0.52:
            status = "Verified"
            score = support_conf
        elif refute_conf >= max(support_conf, uncertain_conf) and refute_conf >= 0.52:
            status = "Hallucination"
            score = 1.0 - refute_conf
        else:
            status = "Plausible"
            score = 0.5 * support_conf + 0.5 * uncertain_conf

        return {
            "status": status,
            "confidence": round(float(score), 4),
            "reasoning": (
                f"consistency model probs: supported={support_conf:.2f}, "
                f"refuted={refute_conf:.2f}, insufficient={uncertain_conf:.2f}"
            ),
            "score": round(float(score), 4),
            "metadata": {"weighted": True, "num_evidence": len(evidence)},
        }


consistency_voter = ConsistencyVoter()
