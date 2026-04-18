import logging
import asyncio
from typing import List
from models.schemas import Claim, Evidence
from services.verification_orchestrator import orchestrator
from services.scraper import scraper, source_scorer

try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS

logger = logging.getLogger("audit-api.verifier")

async def verify_claim(text: str) -> Claim:
    """Full multilayer verification flow: Search -> Scrape -> Vote."""
    logger.info(f"Starting multilayer verification for: {text[:50]}...")
    
    try:
        # 1. Search
        with DDGS() as ddgs:
            search_results = list(ddgs.text(text, max_results=2))
        
        # 2. Scrape & Score Sources
        evidence_list = []
        for res in search_results:
            url = res.get("href", "#")
            scraped_text = await scraper.scrape(url)
            
            # Use snippet if scrape failed
            content = scraped_text if len(scraped_text) > 100 else res.get("body", "")
            
            reliability = source_scorer.score(url, content)
            
            evidence_list.append(Evidence(
                title=res.get("title", "Web Source"),
                snippet=content[:1000], # Keep snippet for voters
                url=url,
                support="supporting", # Initial assumption
                reliability_score=reliability
            ))
            
        if not evidence_list:
            # Fallback: still run ensemble/orchestration so metrics and JSONL collection are preserved
            return await orchestrator.verify_multilayer(text, [])

        # 3. Vote (Ensemble)
        return await orchestrator.verify_multilayer(text, evidence_list)
        
    except Exception as e:
        logger.error(f"Verification flow failed: {str(e)}")
        return Claim(text=text, status="Plausible", confidence=0.0, evidence=[])

async def verify_claims(claims_data: List[dict]) -> List[Claim]:
    """Verify all claims in parallel."""
    tasks = []
    for c in claims_data:
        task = verify_claim(c["text"])
        tasks.append(task)
    
    results = await asyncio.gather(*tasks)
    
    # Re-attach indices
    for i, res in enumerate(results):
        res.start_idx = claims_data[i]["start"]
        res.end_idx = claims_data[i]["end"]
        
    return list(results)

async def verify_claims_stream(claims_data: List[dict]):
    """Stream results as they complete."""
    async def _verify_with_indices(claim_data: dict):
        result = await verify_claim(claim_data["text"])
        return result, claim_data["start"], claim_data["end"]

    tasks = [_verify_with_indices(c) for c in claims_data]
    for task in asyncio.as_completed(tasks):
        result, start, end = await task
        result.start_idx = start
        result.end_idx = end
        yield result
