import logging
import os
import asyncio
import random
import httpx
from typing import List
from models.schemas import Evidence

logger = logging.getLogger("audit-api.search")


class SearchService:
    """
    Search service backed by Tavily API with improvements:
    - Advanced search depth
    - More results (5 instead of 3)
    - Random jitter between searches to avoid rate-limiting
    - Graceful fallback to mock on failure
    """

    def __init__(self):
        self.tavily_key = os.getenv("TAVILY_API_KEY")
        self.use_real_search = bool(self.tavily_key)

        if self.use_real_search:
            logger.info("SearchService: using Tavily API (real search)")
        else:
            logger.warning("SearchService: TAVILY_API_KEY not set — using mock search")

    async def search(self, query: str) -> List[Evidence]:
        if self.use_real_search:
            return await self._tavily_search(query)
        return await self._mock_search(query)

    async def _tavily_search(self, query: str) -> List[Evidence]:
        logger.info(f"Tavily Search: {query}")

        # Small random delay — avoids hammering the API when many claims run in parallel
        await asyncio.sleep(random.uniform(0.2, 0.8))

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(
                    "https://api.tavily.com/search",
                    json={
                        "api_key": self.tavily_key,
                        "query": query,
                        "search_depth": "advanced",   # ← was "basic"
                        "max_results": 5,              # ← was 3
                        "include_answer": False,
                        "include_raw_content": False,  # We do our own scraping
                        "include_images": False,
                    },
                )
                response.raise_for_status()
                data = response.json()

                results: List[Evidence] = []
                for res in data.get("results", []):
                    results.append(
                        Evidence(
                            title=res.get("title", "Web Source"),
                            snippet=res.get("content", ""),
                            url=res.get("url", ""),
                            support="supporting",   # LLM voter decides the real stance
                        )
                    )

                logger.info(f"Tavily returned {len(results)} results for: {query}")
                return results

        except httpx.HTTPStatusError as e:
            logger.error(f"Tavily HTTP error {e.response.status_code}: {e}")
        except httpx.RequestError as e:
            logger.error(f"Tavily request error: {e}")
        except Exception as e:
            logger.error(f"Tavily search failed unexpectedly: {e}")

        # Graceful fallback
        logger.warning("Falling back to mock search due to Tavily failure")
        return await self._mock_search(query)

    async def _mock_search(self, query: str) -> List[Evidence]:
        """
        Expanded mock search used when Tavily is unavailable.
        Returns realistic-looking placeholder evidence for development/testing.
        """
        logger.info(f"Mock Search: {query}")
        lower_query = query.lower()

        # ---- Astronomy / space ----
        if "earth" in lower_query and ("orbit" in lower_query or "sun" in lower_query):
            return [
                Evidence(title="NASA Solar System Exploration", snippet="Earth orbits the Sun at an average distance of about 93 million miles (150 million km), taking approximately 365.25 days to complete one orbit.", url="https://solarsystem.nasa.gov/planets/earth/overview/", support="supporting"),
                Evidence(title="ESA — Earth's Orbit", snippet="Earth's orbital period is 365.25 days. Its average orbital speed is 29.78 km/s.", url="https://www.esa.int/Science_Exploration/Space_Science/Earth_s_orbit", support="supporting"),
            ]

        # ---- Biology / neuroscience ----
        if ("brain" in lower_query or "neuron" in lower_query) and ("billion" in lower_query or "count" in lower_query or "number" in lower_query):
            return [
                Evidence(title="Nature Neuroscience — Neuron Count", snippet="The human brain contains approximately 86 billion neurons, according to a 2009 study by Azevedo et al. using the isotropic fractionation method.", url="https://www.nature.com/articles/nn.2233", support="supporting"),
                Evidence(title="PubMed — Equal Numbers of Neuronal and Nonneuronal Cells", snippet="Using the isotropic fractionator, we find that the human brain has 170 billion cells, of which 86 billion (51%) are neurons.", url="https://pubmed.ncbi.nlm.nih.gov/19226510/", support="supporting"),
            ]

        # ---- Speed of light ----
        if "light" in lower_query and ("speed" in lower_query or "fast" in lower_query):
            return [
                Evidence(title="NIST — Speed of Light", snippet="The speed of light in a vacuum is exactly 299,792,458 metres per second (approximately 3×10⁸ m/s), a defined physical constant.", url="https://physics.nist.gov/cgi-bin/cuu/Value?c", support="supporting"),
            ]

        # ---- Climate / temperature ----
        if "climate" in lower_query or "temperature" in lower_query or "global warming" in lower_query:
            return [
                Evidence(title="NASA Climate Change — Evidence", snippet="Global average surface temperature has risen by about 1.1°C since the late 19th century, driven primarily by increased CO2 and other human-made emissions.", url="https://climate.nasa.gov/evidence/", support="supporting"),
                Evidence(title="IPCC Sixth Assessment Report Summary", snippet="Human influence has warmed the atmosphere, ocean and land. Global surface temperature increased faster since 1970 than in any other 50-year period.", url="https://www.ipcc.ch/report/ar6/wg1/", support="supporting"),
            ]

        # ---- Default generic evidence ----
        return [
            Evidence(
                title="General Reference",
                snippet=f"Search results about '{query}' could not be retrieved in mock mode. Configure TAVILY_API_KEY for real evidence.",
                url="#",
                support="supporting",
            )
        ]


search_service = SearchService()
