from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List

from models.schemas import Evidence


@dataclass
class ClusterSummary:
    num_clusters: int
    independent_clusters: int
    support_score: float


class EvidenceClusterer:
    def assign_clusters(self, evidence: List[Evidence]) -> List[Evidence]:
        if not evidence:
            return evidence

        signatures: Dict[str, int] = {}
        next_id = 0
        for ev in evidence:
            toks = sorted(set(re.findall(r"\w+", ev.snippet.lower())))[:24]
            sig = "|".join(toks)
            cid = signatures.get(sig)
            if cid is None:
                cid = next_id
                signatures[sig] = cid
                next_id += 1
            ev.cluster_id = cid
        return evidence

    def summarize(self, evidence: List[Evidence]) -> ClusterSummary:
        if not evidence:
            return ClusterSummary(0, 0, 0.0)

        if all(ev.cluster_id is None for ev in evidence):
            self.assign_clusters(evidence)

        by_cluster: Dict[int, set[str]] = {}
        for ev in evidence:
            cid = int(ev.cluster_id or 0)
            by_cluster.setdefault(cid, set()).add(ev.source_domain or "")

        num_clusters = len(by_cluster)
        independent_clusters = sum(1 for ds in by_cluster.values() if any(d for d in ds))

        if num_clusters <= 1:
            support = 0.35
        else:
            support = min(0.35 + 0.20 * (num_clusters - 1) + 0.10 * max(0, independent_clusters - 1), 1.0)
        return ClusterSummary(num_clusters, independent_clusters, float(support))


clusterer = EvidenceClusterer()
