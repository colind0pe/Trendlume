import json
from typing import Any
from urllib.parse import unquote


def get_default_domain_for_platform(platform: str) -> str:
    """Return default root cookie domain for a platform."""
    domain_map = {
        "douyin": ".douyin.com",
        "mock": ".mock.com",
        "xiaohongshu": ".xiaohongshu.com",
        "bilibili": ".bilibili.com",
        "tiktok": ".tiktok.com",
    }
    return domain_map.get(platform.lower().strip(), "")


def parse_cookie_string(cookie_str: str, default_domain: str = "") -> list[dict[str, Any]]:
    """Parse a standard Cookie header string into Playwright cookie objects.

    Example: "sessionid=abc123; sid_guard=xyz" -> [{"name": "sessionid", "value": "abc123", ...}]
    """
    cookies: list[dict[str, Any]] = []
    if not cookie_str or not isinstance(cookie_str, str):
        return cookies

    for part in cookie_str.strip().split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        key, val = part.split("=", 1)
        name = key.strip()
        if not name:
            continue

        cookie_dict: dict[str, Any] = {
            "name": name,
            "value": unquote(val.strip()),
            "path": "/",
        }
        if default_domain:
            cookie_dict["domain"] = default_domain
        cookies.append(cookie_dict)

    return cookies


def _sanitize_cookie_list(raw_cookies: list[Any], default_domain: str) -> list[dict[str, Any]]:
    """Sanitize and ensure required domain, path, and security fields on Playwright cookie dictionaries."""
    sanitized: list[dict[str, Any]] = []
    for c in raw_cookies:
        if isinstance(c, dict) and "name" in c and "value" in c:
            item = dict(c)
            item["name"] = str(item["name"]).strip()
            item["value"] = str(item["value"]).strip()
            if not item["name"]:
                continue

            dom = item.get("domain") or default_domain
            if dom:
                item["domain"] = dom
            if not item.get("path"):
                item["path"] = "/"

            # Normalize sameSite for Playwright ("Strict", "Lax", "None")
            if "sameSite" in item:
                ss = str(item["sameSite"]).capitalize()
                if ss in ["Strict", "Lax", "None"]:
                    item["sameSite"] = ss
                    if ss == "None":
                        item["secure"] = True
                else:
                    item.pop("sameSite", None)

            sanitized.append(item)
    return sanitized


def normalize_storage_state(credential_data: Any, platform: str = "") -> dict[str, Any]:
    """Normalize any credential format (raw string, cookie list, dict, JSON string) into

    Playwright storage_state format:
    {
        "cookies": [...],
        "origins": [...]
    }
    """
    default_domain = get_default_domain_for_platform(platform)
    if not credential_data:
        return {"cookies": [], "origins": []}

    # JSON string handling
    if isinstance(credential_data, str):
        trimmed = credential_data.strip()
        if (trimmed.startswith("{") and trimmed.endswith("}")) or (
            trimmed.startswith("[") and trimmed.endswith("]")
        ):
            try:
                return normalize_storage_state(json.loads(trimmed), platform=platform)
            except Exception:
                pass
        return {"cookies": parse_cookie_string(trimmed, default_domain=default_domain), "origins": []}

    # Dict format handling
    if isinstance(credential_data, dict):
        if "cookies" in credential_data and isinstance(credential_data["cookies"], list):
            return {
                "cookies": _sanitize_cookie_list(credential_data["cookies"], default_domain),
                "origins": credential_data.get("origins", []),
            }
        raw_cookie = credential_data.get("cookie") or credential_data.get("raw")
        if isinstance(raw_cookie, str):
            return {"cookies": parse_cookie_string(raw_cookie, default_domain=default_domain), "origins": []}
        # Key-value mapping
        kv_cookies = [
            {"name": str(k), "value": str(v), "path": "/", **({"domain": default_domain} if default_domain else {})}
            for k, v in credential_data.items()
            if isinstance(v, (str, int, float, bool))
        ]
        return {"cookies": kv_cookies, "origins": []}

    # List format handling
    if isinstance(credential_data, list):
        return {"cookies": _sanitize_cookie_list(credential_data, default_domain), "origins": []}

    return {"cookies": [], "origins": []}
