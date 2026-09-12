from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    score: float = 1.0


@runtime_checkable
class SearchProvider(Protocol):
    name: str

    async def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        """Perform search and return structured search results"""
        ...
