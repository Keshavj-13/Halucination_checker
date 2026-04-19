import httpx
import re
import logging
from typing import List, Dict
from urllib.parse import urlparse
from services.source_reliability import source_reliability_scorer

logger = logging.getLogger("audit-api.scraper")

class SourceScorer:
    """Backwards-compatible scorer API forwarding to multifactor scorer."""

    def score(self, url: str, content: str) -> float:
        return source_reliability_scorer.score_page(
            url=url,
            title="Web Source",
            text=content,
            claim_text="",
        ).score

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
