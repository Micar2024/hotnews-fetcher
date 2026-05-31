#!/usr/bin/env python3
"""Fetch hot topics with zhiweidata -> tophub -> vvhan fallback."""

from __future__ import annotations

import argparse
from functools import lru_cache
import json
import logging
import random
import re
from typing import Any, Dict, Iterable, List
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


NewsItem = Dict[str, Any]
logger = logging.getLogger(__name__)

SUPPORTED_PLATFORMS = (
    "微博",
    "抖音",
    "B站",
    "今日头条",
    "百度热点",
    "小红书",
    "知乎热榜",
)

ZHIWEI_PLATFORM_TYPES = {
    "微博": "weibo",
    "抖音": "douyin",
    "B站": "bilibili",
    "今日头条": "toutiao",
    "百度热点": "baidu",
    "小红书": "xiaohongshu",
    "知乎热榜": "zhihu",
}

VVHAN_PLATFORM_KEYS = {
    "微博": ("weibo", "wb", "微博"),
    "抖音": ("douyin", "dy", "抖音"),
    "B站": ("bilibili", "bili", "b站", "B站", "哔哩哔哩"),
    "今日头条": ("toutiao", "头条", "今日头条"),
    "百度热点": ("baidu", "baiduRD", "百度", "百度热点"),
    "小红书": ("xiaohongshu", "xhs", "小红书"),
    "知乎热榜": ("zhihu", "知乎", "知乎热榜"),
}

TOPHUB_PLATFORM_NAMES = {
    "微博": ("微博", "微博热搜"),
    "抖音": ("抖音", "抖音热点"),
    "B站": ("哔哩哔哩", "B站", "bilibili"),
    "今日头条": ("今日头条", "头条"),
    "百度热点": ("百度", "百度热点"),
    "小红书": ("小红书",),
    "知乎热榜": ("知乎", "知乎热榜"),
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
    )
}
TIMEOUT = 10


def get_zhiwei_hotnews(platform: str) -> List[NewsItem]:
    """Fetch hot topics from zhiweidata."""
    _ensure_supported_platform(platform)
    platform_type = ZHIWEI_PLATFORM_TYPES[platform]
    url = "https://trends.zhiweidata.com/hotSearchTrend/search/longTimeInListSearch"
    response = requests.get(
        url,
        params={"type": platform_type, "sortType": "realTime"},
        headers=HEADERS,
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    rows = _first_list_of_dicts(response.json())
    return _normalize_news_list(rows)


def get_tophub_hotnews(platform: str, cnt: int = 10) -> List[NewsItem]:
    """Fetch hot topics from tophub.today by parsing HTML."""
    _ensure_supported_platform(platform)
    home_url = "https://tophub.today/"
    response = requests.get(home_url, headers=HEADERS, timeout=TIMEOUT)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    card = _find_tophub_card(soup, platform)
    if card is None:
        return []

    detail_link = card.find("a", href=True)
    if detail_link:
        detail_url = urljoin(home_url, detail_link["href"])
        detail_response = requests.get(detail_url, headers=HEADERS, timeout=TIMEOUT)
        detail_response.raise_for_status()
        detail_soup = BeautifulSoup(detail_response.text, "html.parser")
        detail_items = _parse_tophub_rows(detail_soup, cnt)
        if detail_items:
            return detail_items

    return _parse_tophub_rows(card, cnt)


def get_vvhan_hotnews() -> List[NewsItem]:
    """Fetch all supported platforms from vvhan hotlist API as one normalized list."""
    platform_items = _get_vvhan_platforms_hotnews()
    items: List[NewsItem] = []
    for platform in SUPPORTED_PLATFORMS:
        items.extend(platform_items.get(platform, []))
    return items


@lru_cache(maxsize=1)
def _get_vvhan_platforms_hotnews() -> Dict[str, List[NewsItem]]:
    """Fetch vvhan hotlist API grouped by supported platform."""
    response = requests.get(
        "https://api.vvhan.com/api/hotlist/all",
        headers=HEADERS,
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    payload = response.json()
    source = payload.get("data", payload) if isinstance(payload, dict) else payload
    platform_items: Dict[str, List[NewsItem]] = {}

    for platform in SUPPORTED_PLATFORMS:
        rows = _find_vvhan_platform_rows(source, platform)
        platform_items[platform] = _normalize_news_list(rows)

    return platform_items


def get_platform_news(platform: str, cnt: int = 10) -> List[NewsItem]:
    """Fetch one platform using zhiweidata, tophub, then vvhan fallback."""
    _ensure_supported_platform(platform)
    limit = _normalize_count(cnt)

    try:
        items = get_zhiwei_hotnews(platform)
        if items:
            return items[:limit]
    except Exception as exc:
        logger.warning("zhiweidata fallback failed for platform=%s: %s", platform, exc)

    try:
        items = get_tophub_hotnews(platform, limit)
        if items:
            return items[:limit]
    except Exception as exc:
        logger.warning("tophub fallback failed for platform=%s: %s", platform, exc)

    try:
        vvhan_items = _get_vvhan_platforms_hotnews().get(platform, [])
        return vvhan_items[:limit]
    except Exception as exc:
        logger.warning("vvhan fallback failed for platform=%s: %s", platform, exc)
        return []


def select_platform_topic(platform: str, cnt: int = 10) -> NewsItem:
    """Select one topic with rank-decay random weight."""
    items = get_platform_news(platform, cnt)
    if not items:
        raise RuntimeError(f"{platform} 暂无可用热搜")
    weights = [1 / ((i + 1) ** 2) for i in range(len(items))]
    return random.choices(items, weights=weights, k=1)[0]


def get_all_platforms_news(cnt: int = 10) -> Dict[str, List[NewsItem]]:
    """Fetch hot topics for all supported platforms."""
    limit = _normalize_count(cnt)
    return {platform: get_platform_news(platform, limit) for platform in SUPPORTED_PLATFORMS}


def _ensure_supported_platform(platform: str) -> None:
    if platform not in SUPPORTED_PLATFORMS:
        supported = "、".join(SUPPORTED_PLATFORMS)
        raise ValueError(f"不支持的平台：{platform}。支持：{supported}")


def _normalize_count(cnt: int) -> int:
    try:
        count = int(cnt)
    except (TypeError, ValueError):
        count = 10
    return max(count, 1)


def _first_list_of_dicts(value: Any) -> List[Dict[str, Any]]:
    if isinstance(value, list):
        dict_rows = [row for row in value if isinstance(row, dict)]
        if dict_rows:
            return dict_rows
        for row in value:
            nested = _first_list_of_dicts(row)
            if nested:
                return nested
    elif isinstance(value, dict):
        for key in ("list", "items", "records", "data", "result", "hotList", "rankList"):
            nested = _first_list_of_dicts(value.get(key))
            if nested:
                return nested
        for nested_value in value.values():
            nested = _first_list_of_dicts(nested_value)
            if nested:
                return nested
    return []


def _normalize_news_list(rows: Iterable[Dict[str, Any]]) -> List[NewsItem]:
    items = []
    for index, row in enumerate(rows):
        item = _normalize_news_item(row, index)
        if item["name"]:
            items.append(item)
    return items


def _normalize_news_item(row: Dict[str, Any], index: int) -> NewsItem:
    name = _first_value(
        row,
        ("name", "title", "keyword", "word", "query", "desc", "eventName", "topic"),
        "",
    )
    rank = _safe_int(_first_value(row, ("rank", "index", "order", "sort"), index + 1), index + 1)
    last_count = _first_value(
        row,
        (
            "lastCount",
            "hotValue",
            "hot",
            "heat",
            "score",
            "rawHot",
            "metrics",
            "count",
            "views",
        ),
        "",
    )
    url = _normalize_url(_first_value(row, ("url", "link", "mobileUrl", "pcUrl", "shareUrl"), ""))
    return {"name": str(name).strip(), "rank": rank, "lastCount": last_count, "url": url}


def _first_value(row: Dict[str, Any], keys: Iterable[str], default: Any = "") -> Any:
    for key in keys:
        value = row.get(key)
        if value is not None and value != "":
            return value
    return default


def _safe_int(value: Any, default: int) -> int:
    if isinstance(value, int):
        return value
    match = re.search(r"\d+", str(value))
    return int(match.group(0)) if match else default


def _normalize_url(value: Any) -> str:
    url = str(value).strip()
    scheme = urlparse(url).scheme.lower()
    return url if scheme in {"http", "https"} else ""


def _find_tophub_card(soup: BeautifulSoup, platform: str):
    names = TOPHUB_PLATFORM_NAMES[platform]
    for card in soup.select(".cc-cd"):
        text = card.get_text(" ", strip=True)
        if any(name in text for name in names):
            return card
    for link in soup.find_all("a", href=True):
        text = link.get_text(" ", strip=True)
        if any(name in text for name in names):
            return link.find_parent(class_="cc-cd") or link.parent or link
    return None


def _parse_tophub_rows(soup, cnt: int) -> List[NewsItem]:
    items: List[NewsItem] = []
    row_candidates = soup.select("table tr")
    if not row_candidates:
        row_candidates = soup.select(".cc-cd-cb-l, .cc-cd-cb-ll, .cc-cd-cb li, .cc-cd-cb a")

    for row in row_candidates:
        link = row.find("a", href=True) if hasattr(row, "find") else None
        text = link.get_text(" ", strip=True) if link else row.get_text(" ", strip=True)
        name = _clean_tophub_title(text)
        if not name:
            continue
        cells = [cell.get_text(" ", strip=True) for cell in row.find_all(["td", "span"])]
        heat = cells[-1] if len(cells) > 1 else ""
        url = urljoin("https://tophub.today/", link["href"]) if link else ""
        items.append(
            {
                "name": name,
                "rank": len(items) + 1,
                "lastCount": heat,
                "url": url,
            }
        )
        if len(items) >= cnt:
            break

    return items


def _clean_tophub_title(text: str) -> str:
    text = re.sub(r"^\s*\d+\s*", "", text or "")
    return text.strip()


def _find_vvhan_platform_rows(source: Any, platform: str) -> List[Dict[str, Any]]:
    keys = VVHAN_PLATFORM_KEYS[platform]
    if isinstance(source, dict):
        for key in keys:
            value = source.get(key)
            if value is not None:
                return _first_list_of_dicts(value)
        for value in source.values():
            rows = _find_vvhan_platform_rows(value, platform)
            if rows:
                return rows
    elif isinstance(source, list):
        for item in source:
            if not isinstance(item, dict):
                continue
            item_name = str(_first_value(item, ("name", "title", "type", "platform"), ""))
            if any(key.lower() in item_name.lower() for key in keys):
                rows = _first_list_of_dicts(item)
                if rows:
                    return rows
    return []


def main() -> None:
    parser = argparse.ArgumentParser(description="热搜三级回退抓取工具")
    parser.add_argument("--platform", choices=SUPPORTED_PLATFORMS, help="要抓取的平台")
    parser.add_argument("--count", type=int, default=10, help="返回条数")
    parser.add_argument("--all", action="store_true", help="抓取全部支持平台")
    parser.add_argument("--select", action="store_true", help="按权重随机选一个选题")
    args = parser.parse_args()

    if args.all:
        data = get_all_platforms_news(args.count)
    elif args.select:
        if not args.platform:
            parser.error("--select 需要同时指定 --platform")
        data = select_platform_topic(args.platform, args.count)
    else:
        if not args.platform:
            parser.error("需要指定 --platform，或使用 --all")
        data = get_platform_news(args.platform, args.count)

    print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
