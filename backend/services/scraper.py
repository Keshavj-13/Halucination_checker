import httpx
import re
import logging
from typing import List, Dict
from urllib.parse import urlparse

logger = logging.getLogger("audit-api.scraper")

class SourceScorer:
    """Evaluates the reliability of a source website."""
    
    TRUSTED_DOMAINS = {
        "gov": 1.0,
        "edu": 0.95,
        "org": 0.8,
        "nature.com": 1.0,
        "science.org": 1.0,
        "reuters.com": 0.9,
        "apnews.com": 0.9,
        "bbc.co.uk": 0.9,
        "wikipedia.org": 0.7, # Good for general, but not primary
    }

    def score(self, url: str, content: str) -> float:
        domain = urlparse(url).netloc.lower()
        
        # 1. Domain Score
        score = 0.5 # Default
        for trusted, val in self.TRUSTED_DOMAINS.items():
            if domain.endswith(trusted):
                score = val
                break
        
        # 2. Content Quality (Heuristic)
        if len(content) > 2000:
            score += 0.1
        if "references" in content.lower() or "citations" in content.lower():
            score += 0.1
            
        return min(score, 1.0)

class WebScraper:
    """Simple scraper to extract main text from URLs."""
    
    async def scrape(self, url: str) -> str:
        logger.info(f"Scraping: {url}")
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                
                # Very basic text extraction (remove script/style tags)
                html = response.text
                text = re.sub(r'<(script|style|nav|footer|header).*?>.*?</\1>', '', html, flags=re.DOTALL | re.IGNORECASE)
                text = re.sub(r'<.*?>', ' ', text)
                text = re.sub(r'\s+', ' ', text).strip()
                
                return text[:5000] # Limit to first 5k chars
        except Exception as e:
            logger.error(f"Scrape failed for {url}: {str(e)}")
            return ""

scraper = WebScraper()
source_scorer = SourceScorer()
