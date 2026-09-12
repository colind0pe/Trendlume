import os
from pathlib import Path
from typing import BinaryIO

from src.core.config import settings
from src.core.exceptions import StorageException
from src.storage.base import StorageService


class LocalStorageService(StorageService):
    """Local filesystem storage implementation with structured directories"""

    SUBDIRS = ["projects", "tasks", "assets", "videos", "audio", "cache"]

    def __init__(self, base_storage_dir: Path = settings.storage_dir):
        self.base_dir = base_storage_dir.resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)
        for subdir in self.SUBDIRS:
            (self.base_dir / subdir).mkdir(parents=True, exist_ok=True)

    def get_path(self, relative_path: str) -> Path:
        # Prevent path traversal attacks
        clean_rel = os.path.normpath(relative_path).lstrip("/\\")
        abs_path = (self.base_dir / clean_rel).resolve()
        if not abs_path.is_relative_to(self.base_dir):
            raise StorageException(f"Illegal path access: {relative_path}")
        return abs_path

    def get_url(self, relative_path: str) -> str:
        clean_rel = relative_path.replace("\\", "/").lstrip("/")
        return f"/api/v1/assets/files/{clean_rel}"

    async def save_file(self, content: bytes, relative_path: str) -> str:
        abs_path = self.get_path(relative_path)
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(abs_path, "wb") as f:
                f.write(content)
            return relative_path.replace("\\", "/").lstrip("/")
        except Exception as e:
            raise StorageException(f"Failed to write file '{relative_path}': {e}")

    async def save_file_stream(self, stream: BinaryIO, relative_path: str) -> str:
        abs_path = self.get_path(relative_path)
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(abs_path, "wb") as f:
                while chunk := stream.read(1024 * 64):
                    f.write(chunk)
            return relative_path.replace("\\", "/").lstrip("/")
        except Exception as e:
            raise StorageException(f"Failed to write file stream '{relative_path}': {e}")

    async def read_file(self, relative_path: str) -> bytes:
        abs_path = self.get_path(relative_path)
        if not abs_path.exists():
            raise StorageException(f"File not found: '{relative_path}'")
        try:
            with open(abs_path, "rb") as f:
                return f.read()
        except Exception as e:
            raise StorageException(f"Failed to read file '{relative_path}': {e}")

    async def delete_file(self, relative_path: str) -> bool:
        abs_path = self.get_path(relative_path)
        if abs_path.exists() and abs_path.is_file():
            abs_path.unlink()
            return True
        return False

    async def exists(self, relative_path: str) -> bool:
        abs_path = self.get_path(relative_path)
        return abs_path.exists() and abs_path.is_file()


local_storage = LocalStorageService()
