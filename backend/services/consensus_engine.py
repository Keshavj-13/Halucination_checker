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

            final_score = float(
                0.42 * det
                + 0.18 * heu
                + 0.00 * sem
                + 0.20 * ent
                + 0.17 * con
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
        return None


consensus_engine = ConsensusEngine()
