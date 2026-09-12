from __future__ import annotations

import asyncio
import ipaddress
import socket
from collections.abc import Iterable
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import httpx

from src.core.exceptions import ProviderException
from src.providers.materials.protocol import MaterialDownload


class StockVideoProvider:
    """Small bounded HTTP helper shared by online-video adapters."""

    name = "stock_video"
    api_host = "api.pexels.com"
    api_hosts = frozenset({"api.pexels.com"})
    download_hosts = frozenset({"videos.pexels.com", "player.vimeo.com"})

    def __init__(
        self,
        api_key: str | None,
        timeout_seconds: float = 15.0,
        download_timeout_seconds: float = 120.0,
        max_download_bytes: int = 200 * 1024 * 1024,
        locale: str = "en-US",
        size: str = "medium",
    ) -> None:
        self.api_key = (api_key or "").strip()
        self.timeout_seconds = max(1.0, float(timeout_seconds))
        self.download_timeout_seconds = max(1.0, float(download_timeout_seconds))
        self.max_download_bytes = max(1, int(max_download_bytes))
        self.locale = locale.strip() or "en-US"
        self.size = size.strip() or "medium"

    def require_key(self) -> str:
        if not self.api_key:
            raise ProviderException(self.name, "Pexels API Key 未配置。")
        return self.api_key

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": self.require_key()}

    async def get_json(
        self,
        url: str,
        *,
        params: dict[str, object] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict:
        self._allow_api_url(url)
        await self._validate_public_host(url)
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds,
                follow_redirects=False,
                trust_env=False,
            ) as client:
                response = await client.get(url, params=params, headers=headers)
                response.raise_for_status()
                payload = response.json()
        except httpx.HTTPStatusError as exc:
            raise ProviderException(self.name, f"Pexels 返回 HTTP {exc.response.status_code}。") from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderException(self.name, f"在线素材请求失败（{type(exc).__name__}）。") from exc
        if not isinstance(payload, dict):
            raise ProviderException(self.name, "在线素材服务返回了无效响应。")
        return payload

    @staticmethod
    def _validate_port(parsed) -> None:
        try:
            port = parsed.port
        except ValueError as exc:
            raise ProviderException("stock_video", "在线素材地址端口无效。") from exc
        if port not in (None, 443):
            raise ProviderException("stock_video", "在线素材地址必须使用 HTTPS 443 端口。")

    @staticmethod
    def _reject_non_public_ip(host: str) -> None:
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            return
        if not address.is_global:
            raise ProviderException("stock_video", "在线素材地址解析到了非公网地址。")

    def _allow_api_url(self, url: str) -> str:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower()
        if (
            parsed.scheme.lower() != "https"
            or host not in self.api_hosts
            or parsed.username
            or parsed.password
        ):
            raise ProviderException(self.name, "Pexels API 地址不在 Provider 允许的域名范围内。")
        self._validate_port(parsed)
        self._reject_non_public_ip(host)
        return url

    def _allow_download_url(self, url: str) -> str:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower()
        if (
            parsed.scheme.lower() != "https"
            or host not in self.download_hosts
            or parsed.username
            or parsed.password
        ):
            if parsed.scheme.lower() != "https":
                raise ProviderException(self.name, "在线素材下载地址必须使用 HTTPS。")
            raise ProviderException(self.name, "在线素材下载地址不在 Provider 允许的域名范围内。")
        self._validate_port(parsed)
        self._reject_non_public_ip(host)
        return url

    async def _validate_public_host(self, url: str) -> None:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower().rstrip(".")
        self._validate_port(parsed)
        self._reject_non_public_ip(host)
        try:
            records = await asyncio.to_thread(
                socket.getaddrinfo,
                host,
                parsed.port or 443,
                type=socket.SOCK_STREAM,
            )
        except OSError as exc:
            raise ProviderException(self.name, "在线素材地址无法解析。") from exc
        addresses = {
            str(record[4][0]).split("%", 1)[0]
            for record in records
            if record and len(record) > 4 and record[4]
        }
        if not addresses:
            raise ProviderException(self.name, "在线素材地址没有可用解析结果。")
        for address in addresses:
            self._reject_non_public_ip(address)

    async def download_url(self, url: str, destination: Path, file_name: str) -> MaterialDownload:
        current = self._allow_download_url(url)
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            async with httpx.AsyncClient(
                timeout=self.download_timeout_seconds,
                follow_redirects=False,
                trust_env=False,
            ) as client:
                for _ in range(4):
                    await self._validate_public_host(current)
                    async with client.stream("GET", current) as response:
                        if response.status_code in {301, 302, 303, 307, 308}:
                            location = response.headers.get("location")
                            if not location:
                                raise ProviderException(self.name, "在线素材重定向缺少目标地址。")
                            current = self._allow_download_url(urljoin(current, location))
                            continue
                        response.raise_for_status()
                        content_length = response.headers.get("content-length")
                        if content_length:
                            try:
                                if int(content_length) > self.max_download_bytes:
                                    raise ProviderException(self.name, "在线素材文件超过 200 MiB 限制。")
                            except ValueError:
                                pass
                        total = 0
                        with destination.open("wb") as output:
                            async for chunk in response.aiter_bytes(chunk_size=64 * 1024):
                                total += len(chunk)
                                if total > self.max_download_bytes:
                                    raise ProviderException(self.name, "在线素材文件超过 200 MiB 限制。")
                                await asyncio.to_thread(output.write, chunk)
                            output.flush()
                        if total <= 0:
                            raise ProviderException(self.name, "在线素材文件为空。")
                        mime_type = (response.headers.get("content-type") or "video/mp4").split(";", 1)[0].strip().lower()
                        if mime_type not in {"video/mp4", "application/mp4", "binary/octet-stream"}:
                            raise ProviderException(self.name, "在线素材不是受支持的 MP4 视频。")
                        return MaterialDownload(
                            file_path=destination,
                            file_name=file_name,
                            mime_type="video/mp4",
                            size_bytes=total,
                        )
                raise ProviderException(self.name, "在线素材重定向次数过多。")
        except ProviderException:
            destination.unlink(missing_ok=True)
            raise
        except httpx.TimeoutException as exc:
            destination.unlink(missing_ok=True)
            raise ProviderException(self.name, "在线素材下载超时。") from exc
        except httpx.HTTPStatusError as exc:
            destination.unlink(missing_ok=True)
            raise ProviderException(self.name, f"在线素材下载失败（HTTP {exc.response.status_code}）。") from exc
        except httpx.HTTPError as exc:
            destination.unlink(missing_ok=True)
            raise ProviderException(self.name, f"在线素材下载失败（{type(exc).__name__}）。") from exc
        except OSError as exc:
            destination.unlink(missing_ok=True)
            raise ProviderException(self.name, "在线素材临时文件写入失败。") from exc
        except asyncio.CancelledError:
            destination.unlink(missing_ok=True)
            raise
        except BaseException:
            destination.unlink(missing_ok=True)
            raise

    @staticmethod
    def orientation_matches(width: int | None, height: int | None, aspect_ratio: str) -> bool:
        if not width or not height:
            return False
        if aspect_ratio == "1:1":
            return abs(float(width) / float(height) - 1.0) <= 0.15
        if aspect_ratio == "9:16":
            return height >= width
        if aspect_ratio == "16:9":
            return width >= height
        return False

    @classmethod
    def pick_rendition(
        cls,
        renditions: Iterable[dict],
        aspect_ratio: str,
        *,
        min_short_edge: int = 720,
        target_width: int | None = None,
        target_height: int | None = None,
    ) -> dict | None:
        valid = []
        for rendition in renditions:
            if not isinstance(rendition, dict) or not rendition.get("link"):
                continue
            file_type = str(rendition.get("file_type") or "").strip().lower()
            if file_type and file_type not in {"video/mp4", "application/mp4"}:
                continue
            width = _positive_int(rendition.get("width"))
            height = _positive_int(rendition.get("height"))
            if not cls.orientation_matches(width, height, aspect_ratio):
                continue
            if min(width or 0, height or 0) < min_short_edge:
                continue
            valid.append({**rendition, "width": width, "height": height})
        if not valid:
            return None

        target_ratio = (
            float(target_width) / float(target_height)
            if target_width and target_height
            else None
        )

        def score(item: dict) -> tuple[float, int, int]:
            width, height = item.get("width") or 0, item.get("height") or 0
            aspect_distance = (
                abs((float(width) / float(height)) - target_ratio)
                if target_ratio and width and height
                else 0.0
            )
            dimension_distance = (
                abs(width - target_width) + abs(height - target_height)
                if target_width and target_height
                else 0
            )
            return (aspect_distance, dimension_distance, -(width * height))

        # Match the target aspect before resolution. This avoids selecting a
        # merely landscape rendition (for example 4:3) for a 16:9 canvas when
        # Pexels returned a closer alternative in the same response.
        if target_width and target_height:
            return min(valid, key=score)
        return max(valid, key=lambda item: (item.get("width") or 0) * (item.get("height") or 0))


def _positive_int(value: object) -> int | None:
    try:
        parsed = int(value) if value is not None else 0
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def safe_pexels_page_url(value: object, *, author: bool = False) -> str | None:
    """Keep only public HTTPS links to official Pexels attribution pages."""
    raw = str(value or "").strip()
    if not raw:
        return None
    parsed = urlsplit(raw)
    host = (parsed.hostname or "").lower().rstrip(".")
    try:
        port = parsed.port
    except ValueError:
        return None
    if (
        parsed.scheme.lower() != "https"
        or host not in {"www.pexels.com", "pexels.com"}
        or port not in (None, 443)
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        return None
    path = parsed.path.rstrip("/")
    if author:
        return raw if path.startswith("/@") and len(path) > 2 else None
    return raw if path.startswith("/video/") and len(path) > 7 else None
