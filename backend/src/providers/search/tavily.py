import httpx
from loguru import logger

from src.core.exceptions import ProviderException
from src.providers.base import mask_secret, retry_async
from src.providers.search.protocol import SearchResult


class TavilySearchProvider:
    name = "tavily"

    def __init__(self, api_key: str, timeout_seconds: float = 15.0):
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    @retry_async(max_retries=2, exceptions=(httpx.HTTPError, httpx.TimeoutException))
    async def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        if not self.api_key:
            raise ProviderException(self.name, "Tavily API key is not configured.")

        logger.info(f"Tavily searching: '{query}' with key {mask_secret(self.api_key)}")
        url = "https://api.tavily.com/search"
        payload = {
            "api_key": self.api_key,
            "query": query,
            "search_depth": "basic",
            "include_answer": False,
            "max_results": max_results,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                res = await client.post(url, json=payload)
                res.raise_for_status()
                data = res.json()
                results = []
                for item in data.get("results", []):
                    results.append(
                        SearchResult(
                            title=item.get("title", ""),
                            url=item.get("url", ""),
                            snippet=item.get("content", ""),
                            score=item.get("score", 1.0),
                        )
                    )
                return results
        except httpx.HTTPStatusError as e:
            raise ProviderException(
                self.name, f"Tavily API HTTP {e.response.status_code}: {e.response.text}"
            ) from e
        except Exception as e:
            raise ProviderException(self.name, f"Tavily Search failed: {e}") from e
