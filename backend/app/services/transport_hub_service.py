from __future__ import annotations

from dataclasses import dataclass
import re

from app.services.amap_client import GeocodingError, search_place_candidates


@dataclass(frozen=True, slots=True)
class TransportHub:
    name: str
    category: str
    latitude: float
    longitude: float
    raw_type: str = ""


AIRPORT_QUERIES = ("{city}机场", "机场")
RAIL_QUERIES = ("{city}高铁站", "{city}火车站", "{city}站")
RAIL_INCLUDE_TOKENS = ("站", "火车", "高铁", "铁路", "动车")
RAIL_EXCLUDE_TOKENS = ("机场", "航站楼", "地铁", "公交", "汽车", "客运", "巴士", "公交站")
HUB_EXCLUDE_TOKENS = (
    "酒店",
    "宾馆",
    "公寓",
    "民宿",
    "客栈",
    "旅馆",
    "住宿",
    "停车场",
    "停车",
    "售楼",
    "住宅",
    "小区",
)

STATIC_TRANSPORT_HUBS: dict[str, tuple[TransportHub, ...]] = {
    "上海": (
        TransportHub("上海虹桥站", "rail", 31.1945, 121.3188, "curated_catalog"),
        TransportHub("上海站", "rail", 31.2494, 121.4558, "curated_catalog"),
        TransportHub("上海虹桥国际机场", "airport", 31.1979, 121.3363, "curated_catalog"),
        TransportHub("上海浦东国际机场", "airport", 31.1443, 121.8083, "curated_catalog"),
    ),
    "北京": (
        TransportHub("北京南站", "rail", 39.8652, 116.3790, "curated_catalog"),
        TransportHub("北京西站", "rail", 39.8948, 116.3210, "curated_catalog"),
        TransportHub("北京首都国际机场", "airport", 40.0801, 116.5846, "curated_catalog"),
        TransportHub("北京大兴国际机场", "airport", 39.5098, 116.4105, "curated_catalog"),
    ),
    "杭州": (
        TransportHub("杭州东站", "rail", 30.2930, 120.2130, "curated_catalog"),
        TransportHub("杭州萧山国际机场", "airport", 30.2360, 120.4320, "curated_catalog"),
    ),
    "西安": (
        TransportHub("西安站", "rail", 34.2770, 108.9630, "curated_catalog"),
        TransportHub("西安北站", "rail", 34.3760, 108.9400, "curated_catalog"),
        TransportHub("西安咸阳国际机场", "airport", 34.4470, 108.7510, "curated_catalog"),
    ),
    "成都": (
        TransportHub("成都东站", "rail", 30.6290, 104.1410, "curated_catalog"),
        TransportHub("成都双流国际机场", "airport", 30.5785, 103.9460, "curated_catalog"),
        TransportHub("成都天府国际机场", "airport", 30.3190, 104.4450, "curated_catalog"),
    ),
    "广州": (
        TransportHub("广州南站", "rail", 22.9900, 113.2690, "curated_catalog"),
        TransportHub("广州白云国际机场", "airport", 23.3920, 113.2990, "curated_catalog"),
    ),
    "深圳": (
        TransportHub("深圳北站", "rail", 22.6090, 114.0300, "curated_catalog"),
        TransportHub("深圳宝安国际机场", "airport", 22.6390, 113.8100, "curated_catalog"),
    ),
    "南京": (
        TransportHub("南京南站", "rail", 31.9700, 118.7970, "curated_catalog"),
        TransportHub("南京禄口国际机场", "airport", 31.7420, 118.8620, "curated_catalog"),
    ),
    "重庆": (
        TransportHub("重庆北站", "rail", 29.6080, 106.5510, "curated_catalog"),
        TransportHub("重庆江北国际机场", "airport", 29.7190, 106.6410, "curated_catalog"),
    ),
    "苏州": (
        TransportHub("苏州站", "rail", 31.3300, 120.6060, "curated_catalog"),
        TransportHub("苏州北站", "rail", 31.4270, 120.6390, "curated_catalog"),
    ),
}


def find_transport_hubs(city: str) -> list[TransportHub]:
    hubs: list[TransportHub] = []
    seen: set[str] = set()

    for query in AIRPORT_QUERIES:
        for candidate in safe_search(query.format(city=city), city):
            hub = candidate_to_hub(candidate, "airport")
            if hub is None or hub.name in seen:
                continue
            hubs.append(hub)
            seen.add(hub.name)

    for query in RAIL_QUERIES:
        for candidate in safe_search(query.format(city=city), city):
            hub = candidate_to_hub(candidate, "rail")
            if hub is None or hub.name in seen:
                continue
            hubs.append(hub)
            seen.add(hub.name)

    for hub in static_transport_hubs_for_city(city):
        if hub.name in seen:
            continue
        hubs.append(hub)
        seen.add(hub.name)

    return sort_hubs(hubs)


def static_transport_hubs_for_city(city: str) -> tuple[TransportHub, ...]:
    normalized = city.replace("市", "").strip()
    return STATIC_TRANSPORT_HUBS.get(normalized, ())


def candidate_to_hub(candidate: dict, category: str) -> TransportHub | None:
    name = str(candidate.get("name") or "").strip()
    raw_type = str(candidate.get("type") or "").strip()
    if not name:
        return None

    searchable = f"{name} {raw_type}"
    if any(token in searchable for token in HUB_EXCLUDE_TOKENS):
        return None

    if category == "airport":
        if "机场" not in searchable:
            return None
    else:
        if any(token in searchable for token in RAIL_EXCLUDE_TOKENS):
            return None
        if not any(token in searchable for token in RAIL_INCLUDE_TOKENS):
            return None

    try:
        return TransportHub(
            name=canonical_hub_name(name, category),
            category=category,
            latitude=float(candidate["latitude"]),
            longitude=float(candidate["longitude"]),
            raw_type=raw_type,
        )
    except (KeyError, TypeError, ValueError):
        return None


def canonical_hub_name(name: str, category: str) -> str:
    """
    Collapse entrances, checkpoints, terminal halls, and plazas to the parent hub.

    A travel planner should recommend "西安站" or "浦东机场", not a random
    check-in entrance returned by place search.
    """
    cleaned = name.strip()
    if category == "rail":
        match = re.match(r"^(.+?站)", cleaned)
        if match:
            return match.group(1)
    if category == "airport":
        match = re.match(r"^(.+?机场)", cleaned)
        if match:
            return match.group(1)
    return re.sub(r"[\(（].*?[)）]", "", cleaned).strip() or cleaned


def sort_hubs(hubs: list[TransportHub]) -> list[TransportHub]:
    return sorted(
        hubs,
        key=lambda hub: (
            0 if hub.category == "airport" else 1,
            hub_name_rank(hub),
            len(hub.name),
            hub.name,
        ),
    )


def hub_name_rank(hub: TransportHub) -> int:
    name = hub.name
    if hub.category == "airport":
        if "国际" in name:
            return 0
        return 1

    if "高铁" in name or "动车" in name:
        return 0
    if any(token in name for token in ("东站", "西站", "南站", "北站", "虹桥")):
        return 1
    if name.endswith("站"):
        return 2
    return 3


def safe_search(keyword: str, city: str) -> list[dict]:
    try:
        return search_place_candidates(keyword=keyword, city=city, offset=10)
    except GeocodingError:
        return []
