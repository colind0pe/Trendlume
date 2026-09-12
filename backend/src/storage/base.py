from pathlib import Path
from typing import BinaryIO, Protocol, runtime_checkable


@runtime_checkable
class StorageService(Protocol):
    """Storage Engine Interface"""

    async def save_file(self, content: bytes, relative_path: str) -> str:
        """Save bytes content to relative path, returns normalized relative path"""
        ...

    async def save_file_stream(self, stream: BinaryIO, relative_path: str) -> str:
        """Save file stream to relative path"""
        ...

    def get_path(self, relative_path: str) -> Path:
        """Resolve full filesystem path safely"""
        ...

    def get_url(self, relative_path: str) -> str:
        """Get public/API access URL for relative path"""
        ...

    async def read_file(self, relative_path: str) -> bytes:
        """Read bytes content of a stored file"""
        ...

    async def delete_file(self, relative_path: str) -> bool:
        """Delete file from storage"""
        ...

    async def exists(self, relative_path: str) -> bool:
        """Check if file exists"""
        ...
