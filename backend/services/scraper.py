import httpx
import re
import asyncio
import random
import logging
from typing import List, Dict, Optional
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

logger = logging.getLogger("audit-api.scraper")

# ---------------------------------------------------------------------------
# Browser-like header pool
# ---------------------------------------------------------------------------
USER_AGENTS = [
    # Chrome on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    # Chrome on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    # Firefox on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    # Firefox on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.4; rv:125.0) Gecko/20100101 Firefox/125.0",
    # Safari on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
    # Edge on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
]

def _get_browser_headers() -> Dict[str, str]:
    """Return a randomised, realistic browser header set."""
    ua = random.choice(USER_AGENTS)
    is_firefox = "Firefox" in ua

    if is_firefox:
        accept = "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
        sec_headers = {}          # Firefox doesn't send Sec-Fetch-* on all requests
    else:
        accept = "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7"
        sec_headers = {
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Sec-CH-UA": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
            "Sec-CH-UA-Mobile": "?0",
            "Sec-CH-UA-Platform": '"Windows"',
        }

    base = {
        "User-Agent": ua,
        "Accept": accept,
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "DNT": "1",
        "Cache-Control": "max-age=0",
    }
    base.update(sec_headers)
    return base


# ---------------------------------------------------------------------------
# robots.txt cache (per origin, so we don't re-fetch for every URL)
# ---------------------------------------------------------------------------
_robots_cache: Dict[str, RobotFileParser] = {}

def _is_allowed(url: str) -> bool:
    """Return True if the URL is allowed by robots.txt, True on any error."""
    try:
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin not in _robots_cache:
            rp = RobotFileParser()
            rp.set_url(f"{origin}/robots.txt")
            rp.read()
            _robots_cache[origin] = rp
        return _robots_cache[origin].can_fetch("*", url)
    except Exception:
        return True   # Allow on error — don't block scraping over a bad robots.txt


# ---------------------------------------------------------------------------
# HTML → clean text (BeautifulSoup when available, regex fallback)
# ---------------------------------------------------------------------------
def _extract_text(html: str) -> str:
    """Extract clean readable text from HTML."""
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")

        # Remove noisy / non-content elements
        for tag in soup(
            ["script", "style", "nav", "footer", "header", "aside",
             "form", "noscript", "iframe", "svg", "button", "input"]
        ):
            tag.decompose()

        # Prefer semantic content containers
        main = (
            soup.find("article")
            or soup.find("main")
            or soup.find(id=re.compile(r"(content|article|post|story)", re.I))
            or soup.find(class_=re.compile(r"(content|article|post|story|body)", re.I))
            or soup.find("body")
        )

        text = main.get_text(separator=" ", strip=True) if main else soup.get_text(separator=" ", strip=True)

    except ImportError:
        # Fallback: raw regex stripping if bs4 not installed
        logger.warning("beautifulsoup4 not installed — falling back to regex HTML stripping")
        text = re.sub(
            r"<(script|style|nav|footer|header|aside|form).*?>.*?</\1>",
            "", html, flags=re.DOTALL | re.IGNORECASE
        )
        text = re.sub(r"<.*?>", " ", text)

    # Normalise whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _smart_truncate(text: str, max_chars: int = 6000) -> str:
    """
    Truncate at a paragraph/sentence boundary rather than mid-word.
    Prefers paragraph breaks, falls back to sentence ends.
    """
    if len(text) <= max_chars:
        return text

    # Try to cut at a paragraph boundary
    chunk = text[:max_chars]
    last_para = chunk.rfind("\n\n")
    if last_para > max_chars * 0.6:
        return chunk[:last_para].strip()

    # Fall back to sentence boundary
    last_sentence = max(chunk.rfind(". "), chunk.rfind("! "), chunk.rfind("? "))
    if last_sentence > max_chars * 0.6:
        return chunk[: last_sentence + 1].strip()

    return chunk.strip()


# ---------------------------------------------------------------------------
# Source Reliability Scorer
# ---------------------------------------------------------------------------
class SourceScorer:
    """Evaluates the reliability of a source website."""

    TRUSTED_DOMAINS: Dict[str, float] = {
        # TLDs
        "gov": 1.0,
        "edu": 0.95,
        "mil": 0.95,
        # Academic / scientific
        "nature.com": 1.0,
        "science.org": 1.0,
        "sciencedirect.com": 0.95,
        "pubmed.ncbi.nlm.nih.gov": 1.0,
        "scholar.google.com": 0.9,
        "arxiv.org": 0.85,
        # Reputable news
        "reuters.com": 0.92,
        "apnews.com": 0.92,
        "bbc.co.uk": 0.90,
        "bbc.com": 0.90,
        "nytimes.com": 0.88,
        "theguardian.com": 0.87,
        "economist.com": 0.87,
        "ft.com": 0.87,
        "wsj.com": 0.85,
        "bloomberg.com": 0.85,
        # Reference
        "wikipedia.org": 0.70,  # Useful but not primary
        "britannica.com": 0.80,
        # General .org
        "org": 0.75,
    }

    def score(self, url: str, content: str) -> float:
        domain = urlparse(url).netloc.lower().lstrip("www.")

        score = 0.5  # Default for unknown domains

        # Exact domain match first, then TLD suffix
        for key, val in self.TRUSTED_DOMAINS.items():
            if domain == key or domain.endswith("." + key) or domain.endswith(key):
                score = val
                break

        # Content quality bonuses
        if len(content) > 3000:
            score += 0.05
        if any(kw in content.lower() for kw in ["references", "citations", "sources", "bibliography"]):
            score += 0.05
        if re.search(r"doi\.org|doi:\s*10\.", content, re.IGNORECASE):
            score += 0.05  # Has academic DOI link

        return min(score, 1.0)


# ---------------------------------------------------------------------------
# Core Web Scraper
# ---------------------------------------------------------------------------
class WebScraper:
    """
    Robust async scraper with:
    - Rotating user-agents + full browser-like headers
    - Automatic retry with exponential back-off
    - Random human-like delays between requests
    - robots.txt compliance
    - BeautifulSoup-based content extraction
    - Smart paragraph-aware truncation
    - Optional Playwright fallback for JS-heavy pages
    """

    MAX_RETRIES = 3
    TIMEOUT = 15.0

    async def scrape(self, url: str) -> str:
        """Main entry point. Returns clean article text or empty string."""
        logger.info(f"Scraping: {url}")

        # 1. robots.txt compliance
        if not _is_allowed(url):
            logger.warning(f"robots.txt disallows scraping: {url}")
            return ""

        # 2. Try standard HTTP scrape with retries
        text = await self._scrape_with_retries(url)

        # 3. If we got very little content, fall back to Playwright (JS rendering)
        if len(text) < 200:
            logger.info(f"Short content ({len(text)} chars), trying Playwright for: {url}")
            text = await self._playwright_scrape(url)

        return _smart_truncate(text)

    async def _scrape_with_retries(self, url: str) -> str:
        """HTTP GET with exponential back-off retries."""
        last_error: Optional[Exception] = None

        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                # Human-like delay (skip on first attempt)
                if attempt > 1:
                    delay = (2 ** (attempt - 1)) + random.uniform(0.5, 1.5)
                    logger.debug(f"Retry {attempt} for {url} after {delay:.1f}s")
                    await asyncio.sleep(delay)
                else:
                    # Small random jitter even on first request
                    await asyncio.sleep(random.uniform(0.3, 1.2))

                async with httpx.AsyncClient(
                    timeout=self.TIMEOUT,
                    follow_redirects=True,
                    http2=True,              # Use HTTP/2 where available (more authentic)
                ) as client:
                    response = await client.get(url, headers=_get_browser_headers())
                    response.raise_for_status()
                    return _extract_text(response.text)

            except httpx.HTTPStatusError as e:
                status = e.response.status_code
                logger.warning(f"HTTP {status} on attempt {attempt} for {url}")
                if status in (403, 404, 410, 451):
                    break   # No point retrying permanent errors
                last_error = e

            except (httpx.RequestError, httpx.TimeoutException) as e:
                logger.warning(f"Request error on attempt {attempt} for {url}: {e}")
                last_error = e

            except Exception as e:
                logger.error(f"Unexpected error on attempt {attempt} for {url}: {e}")
                last_error = e

        logger.error(f"All {self.MAX_RETRIES} attempts failed for {url}: {last_error}")
        return ""

    async def _playwright_scrape(self, url: str) -> str:
        """
        Fallback for JavaScript-heavy pages.
        Requires: pip install playwright && playwright install chromium
        Returns empty string gracefully if Playwright is not installed.
        """
        try:
            from playwright.async_api import async_playwright  # type: ignore

            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=[
                        "--no-sandbox",
                        "--disable-blink-features=AutomationControlled",
                        "--disable-dev-shm-usage",
                    ],
                )
                context = await browser.new_context(
                    user_agent=random.choice(USER_AGENTS),
                    viewport={"width": 1280, "height": 800},
                    locale="en-US",
                    extra_http_headers={
                        "Accept-Language": "en-US,en;q=0.9",
                        "DNT": "1",
                    },
                )
                page = await context.new_page()

                # Block unnecessary resources to speed things up
                await page.route(
                    "**/*.{png,jpg,jpeg,gif,svg,ico,woff,woff2,ttf,eot,css}",
                    lambda route: route.abort(),
                )

                await page.goto(url, wait_until="domcontentloaded", timeout=20000)
                await page.wait_for_timeout(random.randint(1500, 3000))  # simulate reading time

                html = await page.content()
                await browser.close()

                text = _extract_text(html)
                logger.info(f"Playwright extracted {len(text)} chars from {url}")
                return text

        except ImportError:
            logger.info("Playwright not installed — JS fallback unavailable. Install with: pip install playwright && playwright install chromium")
            return ""
        except Exception as e:
            logger.error(f"Playwright scrape failed for {url}: {e}")
            return ""


# ---------------------------------------------------------------------------
# Module-level singletons
# ---------------------------------------------------------------------------
scraper = WebScraper()
source_scorer = SourceScorer()
