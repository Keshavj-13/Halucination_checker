import logging
import asyncio
from typing import List, Dict, Any
from models.schemas import Claim, Evidence
from services.voters.heuristic_voter import heuristic_voter
from services.voters.semantic_voter import semantic_voter
from services.voters.entity_voter import entity_voter
from services.voters.llm_voter import llm_voter
from services.data_collector import data_collector

logger = logging.getLogger("audit-api.orchestrator")

class VerificationOrchestrator:
    """
    Orchestrates the ensemble of voters and calculates weighted consensus.
    """
    
    WEIGHTS = {
        "heuristic": 0.3,
        "semantic": 0.3,
        "entity": 0.2,
        "llm": 0.2
    }

    async def verify_multilayer(self, text: str, evidence: List[Evidence]) -> Claim:
        logger.info(f"Running ensemble for: {text[:50]}...")
        
        # 1. Run all voters in parallel
        voter_names = ["heuristic", "semantic", "entity", "llm"]
        voter_coroutines = [
            heuristic_voter.vote(text, evidence),
            semantic_voter.vote(text, evidence),
            entity_voter.vote(text, evidence),
            llm_voter.vote(text, evidence),
        ]

        raw_results = await asyncio.gather(*voter_coroutines, return_exceptions=True)
        results = {}
        for name, result in zip(voter_names, raw_results):
            if isinstance(result, Exception):
                logger.error(f"Voter {name} failed: {str(result)}")
                results[name] = {
                    "status": "Plausible",
                    "confidence": 0.0,
                    "reasoning": "Voter failed during verification.",
                }
            else:
                results[name] = result

        # 2. Calculate Weighted Consensus
        final_score = 0.0
        status_counts = {"Verified": 0, "Plausible": 0, "Hallucination": 0}
        
        for name, res in results.items():
            weight = self.WEIGHTS.get(name, 0.1)
            
            # Map status to score
            status_val = 1.0 if res["status"] == "Verified" else (0.5 if res["status"] == "Plausible" else 0.0)
            final_score += status_val * weight
            status_counts[res["status"]] = status_counts.get(res["status"], 0) + 1

        # 3. Incorporate Source Reliability
        avg_reliability = sum([ev.reliability_score for ev in evidence]) / len(evidence) if evidence else 0.5
        # Final confidence is a mix of voter consensus and source reliability
        final_confidence = (final_score * 0.7) + (avg_reliability * 0.3)
        
        # Determine final status based on blended confidence
        if final_confidence > 0.75:
            final_status = "Verified"
        elif final_confidence > 0.35:
            final_status = "Plausible"
        else:
            final_status = "Hallucination"

        # 4. Collect Data
        data_collector.collect(text, evidence, results)
        
        return Claim(
            text=text,
            status=final_status,
            confidence=round(final_confidence, 2),
            evidence=evidence,
            voter_scores={name: round(float(res.get("confidence", 0.0)), 2) for name, res in results.items()}
        )

orchestrator = VerificationOrchestrator()
