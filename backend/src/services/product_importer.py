from __future__ import annotations

import asyncio
import html as html_module
import ipaddress
import json
import socket
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import httpx

from src.core.exceptions import ValidationException


@dataclass(slots=True)
class ParsedProduct:
    title: str = ""
    brand: str = ""
    description: str = ""
    price: str = ""
    currency: str = ""
    specifications: dict[str, str] = field(default_factory=dict)
    images: list[str] = field(default_factory=list)
    field_sources: dict[str, str] = field(default_factory=dict)
    source_snapshot: dict = field(default_factory=dict)


class _ProductHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self.images: list[str] = []
        self.title_parts: list[str] = []
        self.h1_parts: list[str] = []
        self._capture: str | None = None
        self._script_type = ""
        self._script_parts: list[str] = []
        self.json_ld: list[str] = []
        self.itemprop_values: dict[str, list[str]] = {}

    def handle_starttag(self, tag: str, attrs) -> None:
        values = {str(key).lower(): str(value or "") for key, value in attrs}
        tag_name = tag.lower()
        if tag_name == "meta":
            key = values.get("property") or values.get("name") or values.get("itemprop")
            if key and values.get("content"):
                self.meta[key.lower()] = values["content"].strip()
        elif tag_name == "img":
            image = values.get("src") or values.get("data-src") or values.get("data-lazy-src")
            if image:
                self.images.append(image.strip())
        elif tag_name == "title":
            self._capture = "title"
        elif tag_name == "h1":
            self._capture = "h1"
        elif tag_name == "script":
            self._script_type = values.get("type", "").lower()
            if "ld+json" in self._script_type:
                self._capture = "jsonld"
                self._script_parts = []
        itemprop = values.get("itemprop")
        if itemprop:
            value = values.get("content") or values.get("value")
            if value:
                self.itemprop_values.setdefault(itemprop.lower(), []).append(value.strip())

    def handle_endtag(self, tag: str) -> None:
        tag_name = tag.lower()
        if tag_name == "script" and self._capture == "jsonld":
            self.json_ld.append("".join(self._script_parts))
            self._capture = None
            self._script_parts = []
            self._script_type = ""
        elif tag_name == "title" and self._capture == "title":
            self._capture = None
        elif tag_name == "h1" and self._capture == "h1":
            self._capture = None

    def handle_data(self, data: str) -> None:
        if self._capture == "title":
            self.title_parts.append(data)
        elif self._capture == "h1":
            self.h1_parts.append(data)
        elif self._capture == "jsonld":
            self._script_parts.append(data)


def _clean(value: object) -> str:
    return " ".join(html_module.unescape(str(value or "")).split()).strip()


def _first(value: object) -> str:
    if isinstance(value, (list, tuple)):
        return _clean(value[0]) if value else ""
    if isinstance(value, dict):
        return _clean(value.get("name") or value.get("value") or "")
    return _clean(value)


def _product_nodes(value: object) -> list[dict]:
    if isinstance(value, list):
        result: list[dict] = []
        for item in value:
            result.extend(_product_nodes(item))
        return result
    if not isinstance(value, dict):
        return []
    node_type = value.get("@type")
    types = node_type if isinstance(node_type, list) else [node_type]
    result = [value] if any(str(item).casefold() == "product" for item in types) else []
    result.extend(_product_nodes(value.get("@graph")))
    return result


def _safe_image_url(value: object, source_url: str) -> str | None:
    candidate = urljoin(source_url, _clean(value))
    parsed = urlsplit(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return candidate


def parse_product_html(markup: str, source_url: str) -> ParsedProduct:
    """Parse product facts with JSON-LD first, then OpenGraph, then page structure."""
    parser = _ProductHTMLParser()
    parser.feed(markup)
    json_products: list[dict] = []
    for raw in parser.json_ld:
        try:
            json_products.extend(_product_nodes(json.loads(raw)))
        except (TypeError, json.JSONDecodeError):
            continue

    product = json_products[0] if json_products else {}
    offer = product.get("offers") if isinstance(product, dict) else {}
    if isinstance(offer, list):
        offer = offer[0] if offer else {}
    offer = offer if isinstance(offer, dict) else {}
    brand = product.get("brand") if isinstance(product, dict) else ""
    title = _first(product.get("name")) if product else ""
    description = _first(product.get("description")) if product else ""
    price = _first(offer.get("price"))
    currency = _first(offer.get("priceCurrency"))
    field_sources: dict[str, str] = {}

    def choose(field_name: str, current: str, candidates: list[tuple[str, str]]) -> str:
        if current:
            field_sources[field_name] = candidates[0][0]
            return current
        for source_type, value in candidates:
            if value:
                field_sources[field_name] = source_type
                return value
        return ""

    title = choose(
        "title",
        title,
        [("json_ld", ""), ("opengraph", _clean(parser.meta.get("og:title"))), ("page_structure", _clean(parser.h1_parts)) or _clean(parser.title_parts)],
    )
    brand = choose(
        "brand",
        _first(brand),
        [("json_ld", ""), ("opengraph", _clean(parser.meta.get("product:brand"))), ("page_structure", _first(parser.itemprop_values.get("brand")))],
    )
    description = choose(
        "description",
        description,
        [("json_ld", ""), ("opengraph", _clean(parser.meta.get("og:description"))), ("page_structure", _clean(parser.meta.get("description")))],
    )
    price = choose(
        "price",
        price,
        [("json_ld", ""), ("opengraph", _clean(parser.meta.get("product:price:amount"))), ("page_structure", _first(parser.itemprop_values.get("price")))],
    )
    currency = choose(
        "currency",
        currency,
        [("json_ld", ""), ("opengraph", _clean(parser.meta.get("product:price:currency"))), ("page_structure", _first(parser.itemprop_values.get("priceCurrency")))],
    )

    specifications: dict[str, str] = {}
    for key in ("sku", "mpn", "gtin", "gtin8", "gtin12", "gtin13", "gtin14"):
        value = _first(product.get(key)) if product else ""
        if value:
            specifications[key] = value
            field_sources[f"specifications.{key}"] = "json_ld"
    properties = product.get("additionalProperty") if product else []
    if isinstance(properties, dict):
        properties = [properties]
    for item in properties if isinstance(properties, list) else []:
        if not isinstance(item, dict):
            continue
        key = _clean(item.get("name"))
        value = _clean(item.get("value"))
        if key and value:
            specifications[key] = value
            field_sources[f"specifications.{key}"] = "json_ld"
    for key, values in parser.itemprop_values.items():
        if key in {"sku", "mpn", "gtin", "gtin8", "gtin12", "gtin13", "gtin14"} and key not in specifications:
            value = _first(values)
            if value:
                specifications[key] = value
                field_sources[f"specifications.{key}"] = "page_structure"

    raw_images: list[object] = []
    if product:
        raw_images.extend(product.get("image") if isinstance(product.get("image"), list) else [product.get("image")])
    raw_images.extend([parser.meta.get("og:image"), *parser.images])
    images = list(dict.fromkeys(filter(None, (_safe_image_url(item, source_url) for item in raw_images))))[:20]
    source_snapshot = {
        "url": source_url,
        "parser_order": ["json_ld", "opengraph", "page_structure"],
        "json_ld_product_found": bool(json_products),
        "field_sources": field_sources,
        "image_count": len(images),
    }
    return ParsedProduct(
        title=title,
        brand=brand,
        description=description,
        price=price,
        currency=currency,
        specifications=specifications,
        images=images,
        field_sources=field_sources,
        source_snapshot=source_snapshot,
    )


def validate_public_url(url: str) -> str:
    """Validate a public HTTP URL before any server-side request is made."""
    value = str(url or "").strip()
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise ValidationException("商品 URL 格式无效。") from exc
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValidationException("商品 URL 只支持公开的 HTTP 或 HTTPS 地址。")
    if parsed.username or parsed.password:
        raise ValidationException("商品 URL 不能包含账号或密码。")
    if port not in {None, 80, 443}:
        raise ValidationException("商品 URL 的端口不受支持。")
    host = parsed.hostname.rstrip(".").lower()
    try:
        addresses = [ipaddress.ip_address(host)]
    except ValueError:
        try:
            addresses = [
                ipaddress.ip_address(item[4][0])
                for item in socket.getaddrinfo(host, port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
            ]
        except (OSError, ValueError) as exc:
            raise ValidationException("无法解析商品 URL 的公开地址。") from exc
    if not addresses or any(
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
        or address.is_multicast
        or address.is_unspecified
    for address in addresses):
        raise ValidationException("为保护服务器安全，不允许抓取内网或保留地址。")
    return value


class ProductImporter:
    MAX_HTML_BYTES = 2 * 1024 * 1024
    MAX_MEDIA_BYTES = 12 * 1024 * 1024
    MAX_REDIRECTS = 3
    DNS_TIMEOUT_SECONDS = 3.0
    TIMEOUT = httpx.Timeout(connect=3.0, read=8.0, write=8.0, pool=3.0)

    async def _validated_url(self, url: str) -> str:
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(validate_public_url, url),
                timeout=self.DNS_TIMEOUT_SECONDS,
            )
        except TimeoutError as exc:
            raise ValidationException("商品 URL 地址解析超时，请稍后重试。") from exc

    async def _fetch(self, url: str, *, max_bytes: int) -> tuple[bytes, str, str]:
        current = await self._validated_url(url)
        # Do not inherit process-wide proxy settings. A proxy can otherwise
        # turn a public-looking URL into an unintended internal request path.
        async with httpx.AsyncClient(
            timeout=self.TIMEOUT,
            follow_redirects=False,
            trust_env=False,
        ) as client:
            for _ in range(self.MAX_REDIRECTS + 1):
                current = await self._validated_url(current)
                try:
                    async with client.stream("GET", current, headers={"Accept": "text/html,image/*;q=0.9,*/*;q=0.1"}) as response:
                        if response.status_code in {301, 302, 303, 307, 308}:
                            location = response.headers.get("location")
                            if not location:
                                raise ValidationException("商品页面重定向缺少目标地址。")
                            current = urljoin(current, location)
                            continue
                        if response.status_code >= 400:
                            raise ValidationException(f"商品页面抓取失败（HTTP {response.status_code}）。")
                        content_length = response.headers.get("content-length")
                        if content_length:
                            try:
                                declared_size = int(content_length)
                            except ValueError as exc:
                                raise ValidationException("商品页面或素材大小声明无效。") from exc
                            if declared_size < 0 or declared_size > max_bytes:
                                raise ValidationException("商品页面或素材超过大小限制。")
                        chunks: list[bytes] = []
                        size = 0
                        async for chunk in response.aiter_bytes(64 * 1024):
                            size += len(chunk)
                            if size > max_bytes:
                                raise ValidationException("商品页面或素材超过大小限制。")
                            chunks.append(chunk)
                        return b"".join(chunks), response.headers.get("content-type", ""), current
                except httpx.TimeoutException as exc:
                    raise ValidationException("商品页面抓取超时，请稍后重试。") from exc
                except httpx.HTTPError as exc:
                    raise ValidationException("商品页面抓取失败，请检查公开地址。") from exc
            raise ValidationException("商品页面重定向次数过多。")

    async def fetch_html(self, url: str) -> tuple[str, str]:
        content, content_type, final_url = await self._fetch(url, max_bytes=self.MAX_HTML_BYTES)
        if content_type and "html" not in content_type.lower() and "text/" not in content_type.lower():
            raise ValidationException("商品 URL 不是可解析的 HTML 页面。")
        try:
            return content.decode("utf-8", errors="replace"), final_url
        except UnicodeDecodeError as exc:
            raise ValidationException("商品页面编码无法解析。") from exc

    async def fetch_media(self, url: str) -> tuple[bytes, str, str]:
        content, content_type, final_url = await self._fetch(url, max_bytes=self.MAX_MEDIA_BYTES)
        return content, content_type.split(";", 1)[0].strip().lower(), final_url
