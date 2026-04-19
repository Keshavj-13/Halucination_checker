from __future__ import annotations

import json
import re
from typing import Dict, Tuple

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression

from services.config import CALIBRATOR_MODEL_PATH, PROCESSED_DATA_DIR, CONSENSUS_USE_CALIBRATOR


class ConsensusEngine:
    def __init__(self):
        self.calibrator = None
        if CALIBRATOR_MODEL_PATH.exists():
            self.calibrator = joblib.load(CALIBRATOR_MODEL_PATH)
        else:
            self.calibrator = self._fit_bootstrap_calibrator()

    @staticmethod
    def _status_to_score(status: str, confidence: float) -> float:
        s = (status or "Plausible").lower()
        c = max(0.0, min(float(confidence), 1.0))
        if s == "verified":
            return 0.5 + 0.5 * c
        if s == "hallucination":
            return 0.5 * (1.0 - c)
        return 0.25 + 0.5 * c

    def _feature_vector(self, voter_results: Dict[str, Dict], source_reliability: float, cluster_support: float) -> np.ndarray:
        ordered = ["heuristic", "semantic", "entity", "consistency", "deterministic"]
        feats = []
        for v in ordered:
            r = voter_results.get(v, {})
            feats.append(self._status_to_score(r.get("status", "Plausible"), r.get("confidence", 0.0)))
            feats.append(float(r.get("confidence", 0.0)))
        feats.extend([float(source_reliability), float(cluster_support)])
        return np.asarray(feats, dtype=np.float32).reshape(1, -1)

    def combine(self, voter_results: Dict[str, Dict], source_reliability: float, cluster_support: float) -> Tuple[float, float, str, Dict[str, float]]:
        x = self._feature_vector(voter_results, source_reliability, cluster_support)
        if self.calibrator is not None and CONSENSUS_USE_CALIBRATOR:
            try:
                p = self.calibrator.predict_proba(x)[0]
                classes = [str(c).lower() for c in getattr(self.calibrator, "classes_", [])]
                p_h = p_p = p_v = 0.0

                if len(classes) == len(p):
                    for cls, prob in zip(classes, p):
                        val = float(prob)
                        if cls in {"hallucination", "refuted", "refute", "contradiction"}:
                            p_h = val
                        elif cls in {"verified", "supported", "support", "entails"}:
                            p_v = val
                        elif cls in {"plausible", "insufficient", "uncertain"}:
                            p_p = val
                else:
                    if len(p) == 3:
                        p_h, p_p, p_v = [float(v) for v in p]
                    else:
                        p_v = float(p[-1])
                        p_h = 1.0 - p_v
                        p_p = 0.0

                total = max(1e-8, p_h + p_p + p_v)
                p_h, p_p, p_v = p_h / total, p_p / total, p_v / total
                final_score = p_v + 0.5 * p_p
                confidence = max(p_h, p_p, p_v)
            except Exception:
                # Feature drift fallback: use deterministic weighted fusion.
                det = self._status_to_score(voter_results.get("deterministic", {}).get("status", "Plausible"), voter_results.get("deterministic", {}).get("confidence", 0.0))
                heu = self._status_to_score(voter_results.get("heuristic", {}).get("status", "Plausible"), voter_results.get("heuristic", {}).get("confidence", 0.0))
                sem = self._status_to_score(voter_results.get("semantic", {}).get("status", "Plausible"), voter_results.get("semantic", {}).get("confidence", 0.0))
                ent = self._status_to_score(voter_results.get("entity", {}).get("status", "Plausible"), voter_results.get("entity", {}).get("confidence", 0.0))
                con = self._status_to_score(voter_results.get("consistency", {}).get("status", "Plausible"), voter_results.get("consistency", {}).get("confidence", 0.0))

                weighted = (
                    0.39 * det
                    + 0.16 * heu
                    + 0.19 * sem
                    + 0.12 * ent
                    + 0.11 * con
                    + 0.02 * float(source_reliability)
                    + 0.01 * float(cluster_support)
                )
                final_score = float(weighted)
                confidence = abs(final_score - 0.5) * 2.0
        else:
            det = self._status_to_score(voter_results.get("deterministic", {}).get("status", "Plausible"), voter_results.get("deterministic", {}).get("confidence", 0.0))
            heu = self._status_to_score(voter_results.get("heuristic", {}).get("status", "Plausible"), voter_results.get("heuristic", {}).get("confidence", 0.0))
            sem = self._status_to_score(voter_results.get("semantic", {}).get("status", "Plausible"), voter_results.get("semantic", {}).get("confidence", 0.0))
            ent = self._status_to_score(voter_results.get("entity", {}).get("status", "Plausible"), voter_results.get("entity", {}).get("confidence", 0.0))
            con = self._status_to_score(voter_results.get("consistency", {}).get("status", "Plausible"), voter_results.get("consistency", {}).get("confidence", 0.0))

            # Cluster support kept auxiliary (small weight), deterministic voter primary.
            final_score = float(
                0.39 * det
                + 0.16 * heu
                + 0.19 * sem
                + 0.12 * ent
                + 0.11 * con
                + 0.02 * float(source_reliability)
                + 0.01 * float(cluster_support)
            )
            confidence = abs(final_score - 0.5) * 2.0

        if final_score >= 0.68:
            label = "Verified"
        elif final_score <= 0.38:
            label = "Hallucination"
        else:
            label = "Plausible"

        normalized = {k: self._status_to_score(v.get("status", "Plausible"), v.get("confidence", 0.0)) for k, v in voter_results.items()}
        return float(final_score), float(min(max(confidence, 0.0), 1.0)), label, normalized

    def _fit_bootstrap_calibrator(self):
        train_path = PROCESSED_DATA_DIR / "consistency_train.jsonl"
        if not train_path.exists():
            return None

        X, y = [], []
        with train_path.open("r", encoding="utf-8") as f:
            for i, line in enumerate(f):
                if i >= 50000:
                    break
                if not line.strip():
                    continue
                row = json.loads(line)
                claim = row.get("claim", "")
                evidence = row.get("evidence", "")
                label = row.get("label", "insufficient").lower()

                c = set(re.findall(r"\w+", claim.lower()))
                e = set(re.findall(r"\w+", evidence.lower()))
                inter = len(c & e)
                c_len = max(1, len(c))
                union = max(1, len(c | e))

                lexical = inter / c_len
                jacc = inter / union
                years_c = set(re.findall(r"\b(19\d{2}|20\d{2})\b", claim))
                years_e = set(re.findall(r"\b(19\d{2}|20\d{2})\b", evidence))
                year_match = len(years_c & years_e) / max(1, len(years_c)) if years_c else 0.7

                nums_c = [float(x) for x in re.findall(r"\b\d+(?:\.\d+)?\b", claim)]
                nums_e = [float(x) for x in re.findall(r"\b\d+(?:\.\d+)?\b", evidence)]
                num_match = (
                    sum(1 for n in nums_c if any(abs(n - m) <= max(1.0, 0.02 * abs(n)) for m in nums_e)) / len(nums_c)
                    if nums_c else 0.7
                )

                entity = 0.5 * year_match + 0.5 * num_match
                consistency = 0.45 * lexical + 0.35 * jacc + 0.20 * entity
                deterministic_proxy = min(1.0, 0.40 * lexical + 0.40 * entity + 0.2)
                reliability = min(1.0, 0.45 + 0.35 * jacc)
                cluster = min(1.0, 0.2 + 0.8 * jacc)

                pseudo = [
                    ("verified" if lexical > 0.62 else "plausible" if lexical > 0.32 else "hallucination", lexical),
                    ("verified" if jacc > 0.55 else "plausible" if jacc > 0.25 else "hallucination", jacc),
                    ("verified" if entity > 0.70 else "plausible" if entity > 0.35 else "hallucination", entity),
                    ("verified" if consistency > 0.65 else "plausible" if consistency > 0.35 else "hallucination", consistency),
                    ("verified" if deterministic_proxy > 0.60 else "plausible" if deterministic_proxy > 0.35 else "hallucination", deterministic_proxy),
                ]

                feats = []
                for s, conf in pseudo:
                    feats.append(self._status_to_score(s, conf))
                    feats.append(float(conf))
                feats += [reliability, cluster]
                X.append(feats)

                if label == "supported":
                    y.append("verified")
                elif label == "refuted":
                    y.append("hallucination")
                else:
                    y.append("plausible")

        if not X:
            return None
        clf = LogisticRegression(max_iter=700)
        clf.fit(np.asarray(X, dtype=np.float32), np.asarray(y))
        return clf


consensus_engine = ConsensusEngine()
