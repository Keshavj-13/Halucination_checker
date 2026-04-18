import logging
import os
import httpx
from typing import List
from models.schemas import Evidence

logger = logging.getLogger("audit-api.search")

class SearchService:
    def __init__(self):
        self.tavily_key = os.getenv("TAVILY_API_KEY")
        self.use_real_search = bool(self.tavily_key)

    async def search(self, query: str) -> List[Evidence]:
        if self.use_real_search:
            return await self._tavily_search(query)
        return await self._mock_search(query)

    async def _tavily_search(self, query: str) -> List[Evidence]:
        logger.info(f"Tavily Search: {query}")
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    "https://api.tavily.com/search",
                    json={
                        "api_key": self.tavily_key,
                        "query": query,
                        "search_depth": "basic",
                        "max_results": 3
                    }
                )
                response.raise_for_status()
                data = response.json()
                
                results = []
                for res in data.get("results", []):
                    results.append(Evidence(
                        title=res.get("title", "Web Source"),
                        snippet=res.get("content", ""),
                        url=res.get("url", ""),
                        support="supporting" # Default to supporting, LLM will decide
                    ))
                return results
        except Exception as e:
            logger.error(f"Tavily search failed: {str(e)}")
            return await self._mock_search(query)

    async def _mock_search(self, query: str) -> List[Evidence]:
        logger.info(f"Mock Search: {query}")
        lower_query = query.lower()
        
        if "earth" in lower_query and "orbit" in lower_query:
            return [Evidence(title="NASA", snippet="Earth orbits the Sun at 93m miles.", url="https://nasa.gov", support="supporting")]
        elif "brain" in lower_query and "neuron" in lower_query:
            return [Evidence(title="Nature", snippet="The brain has 86 billion neurons.", url="https://nature.com", support="supporting")]
        
        return [Evidence(title="General Source", snippet=f"Information about {query}...", url="#", support="supporting")]

search_service = SearchService()
