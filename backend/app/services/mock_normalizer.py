from __future__ import annotations

from app.schemas import (
    HotelInput,
    HotelStay,
    NormalizedPOI,
    POIProfile,
    POIType,
    POIVisitStyle,
    RawPOIInput,
    TimeBlockType,
)
from app.services.amap_client import GeocodingError, geocode_place_details, search_place_candidates


DEFAULT_DURATIONS = {
    POIType.SCENIC: 75,
    POIType.RESTAURANT: 60,
}


def normalize_poi(
    raw_poi: RawPOIInput,
    poi_type: POIType,
    city: str | None = None,
) -> NormalizedPOI:
    """
    Normalize a raw POI with live Amap POI search/geocoding and default MVP durations.
    """
    external_poi = best_place_candidate(raw_poi.name, city)
    if (
        external_poi is not None
        and external_poi.get("latitude") is not None
        and external_poi.get("longitude") is not None
    ):
        profile = infer_poi_profile(raw_poi.name, poi_type, external_poi)
        return NormalizedPOI(
            name=raw_poi.name,
            type=poi_type,
            city=city,
            latitude=float(external_poi["latitude"]),
            longitude=float(external_poi["longitude"]),
            duration_minutes=raw_poi.resolved_duration_minutes or profile.typical_duration_minutes,
            profile=profile,
            fixed_day=raw_poi.fixed_day,
            fixed_time_start=raw_poi.fixed_time_start,
            fixed_time_end=raw_poi.fixed_time_end,
            intent_ownership=raw_poi.intent_ownership,
        )

    geocode = geocode_place_details(raw_poi.name, city=city)
    city_name = normalize_city_name(geocode.get("city"), geocode.get("province"))
    profile = infer_poi_profile(raw_poi.name, poi_type, external_poi)
    return NormalizedPOI(
        name=raw_poi.name,
        type=poi_type,
        city=city_name,
        latitude=geocode["latitude"],
        longitude=geocode["longitude"],
        duration_minutes=raw_poi.resolved_duration_minutes or profile.typical_duration_minutes,
        profile=profile,
        fixed_day=raw_poi.fixed_day,
        fixed_time_start=raw_poi.fixed_time_start,
        fixed_time_end=raw_poi.fixed_time_end,
        intent_ownership=raw_poi.intent_ownership,
    )


def normalize_hotel(hotel: HotelInput, city: str | None = None) -> HotelStay:
    """
    Normalize a hotel with live Amap geocoding.
    """
    geocode = geocode_place_details(hotel.name, city=city)
    return HotelStay(
        name=hotel.name,
        city=normalize_city_name(geocode.get("city"), geocode.get("province")),
        latitude=geocode["latitude"],
        longitude=geocode["longitude"],
    )


def normalize_anchor(name: str, city: str | None = None) -> HotelStay:
    """
    Normalize an arrival/departure anchor into the same internal shape as a hotel.
    """
    external_poi = best_place_candidate(name, city)
    if (
        external_poi is not None
        and external_poi.get("latitude") is not None
        and external_poi.get("longitude") is not None
    ):
        return HotelStay(
            name=name,
            city=city,
            latitude=float(external_poi["latitude"]),
            longitude=float(external_poi["longitude"]),
        )

    geocode = geocode_place_details(name, city=city)
    return HotelStay(
        name=name,
        city=normalize_city_name(geocode.get("city"), geocode.get("province")),
        latitude=geocode["latitude"],
        longitude=geocode["longitude"],
    )


def estimate_poi_duration(name: str, poi_type: POIType) -> int:
    return infer_poi_profile(name, poi_type).typical_duration_minutes


def infer_poi_profile(
    name: str,
    poi_type: POIType,
    external_poi: dict | None = None,
) -> POIProfile:
    normalized = name.casefold()
    external_type = str(external_poi.get("type") or "").casefold() if external_poi else ""
    external_business_area = normalize_business_area(external_poi.get("business_area")) if external_poi else ""

    if poi_type == POIType.RESTAURANT:
        external_restaurant_profile = infer_restaurant_profile_from_external(
            external_type=external_type,
            business_area=external_business_area,
        )
        if external_restaurant_profile is not None:
            return external_restaurant_profile
        if contains_any(normalized, ("咖啡", "coffee", "bakery", "面包", "甜品", "dessert", "茶")):
            return POIProfile(
                visit_style=POIVisitStyle.FOOD_STOP,
                best_time_blocks=[TimeBlockType.AFTERNOON],
                typical_duration_minutes=45,
                intensity="light",
                signal_source="external",
                signal_summary="高德类型偏咖啡或甜品，通常更适合放在下午。",
            )
        if contains_any(normalized, ("小吃", "snack", "food street", "夜市", "夜宵")):
            return POIProfile(
                visit_style=POIVisitStyle.FOOD_DISTRICT,
                best_time_blocks=[TimeBlockType.EVENING],
                typical_duration_minutes=60,
                intensity="medium",
            )
        if contains_any(normalized, ("火锅", "hotpot", "烤肉", "烧烤", "宴")):
            return POIProfile(
                visit_style=POIVisitStyle.FOOD_STOP,
                best_time_blocks=[TimeBlockType.EVENING],
                typical_duration_minutes=90,
                intensity="medium",
            )
        return POIProfile(
            visit_style=POIVisitStyle.FOOD_STOP,
            best_time_blocks=[TimeBlockType.AFTERNOON, TimeBlockType.EVENING],
            typical_duration_minutes=DEFAULT_DURATIONS[poi_type],
            intensity="medium",
        )

    external_scenic_profile = infer_scenic_profile_from_external(
        external_type=external_type,
        business_area=external_business_area,
    )
    if external_scenic_profile is not None:
        return external_scenic_profile

    if contains_any(normalized, ("博物馆", "museum", "美术馆", "gallery", "展览", "科技馆", "自然")):
        return POIProfile(
            visit_style=POIVisitStyle.MUSEUM,
            best_time_blocks=[TimeBlockType.MORNING, TimeBlockType.AFTERNOON],
            typical_duration_minutes=150,
            intensity="heavy",
        )
    if contains_any(normalized, ("动物园", "zoo", "水族馆", "aquarium", "乐园", "disney", "环球")):
        return POIProfile(
            visit_style=POIVisitStyle.LANDMARK,
            best_time_blocks=[TimeBlockType.MORNING, TimeBlockType.AFTERNOON],
            typical_duration_minutes=180,
            intensity="heavy",
        )
    if contains_any(normalized, ("公园", "park", "植物园", "garden", "寺", "庙", "教堂")):
        return POIProfile(
            visit_style=POIVisitStyle.TEMPLE_PARK,
            best_time_blocks=[TimeBlockType.MORNING, TimeBlockType.AFTERNOON],
            typical_duration_minutes=90,
            intensity="medium",
        )
    if contains_any(normalized, ("外滩", "滨江", "tower", "塔", "观景", "夜景", "洪崖洞", "江景", "river", "bund")):
        return POIProfile(
            visit_style=POIVisitStyle.NIGHT_VIEW,
            best_time_blocks=[TimeBlockType.EVENING],
            typical_duration_minutes=60,
            intensity="light",
        )
    if contains_any(normalized, ("步行街", "老街", "古镇", "路", "里弄", "街区", "田子坊", "新天地", "公馆", "巷子")):
        return POIProfile(
            visit_style=POIVisitStyle.OLD_STREET,
            best_time_blocks=[TimeBlockType.AFTERNOON, TimeBlockType.EVENING],
            typical_duration_minutes=75,
            intensity="medium",
        )
    if contains_any(normalized, ("广场", "地标", "塔", "城门", "古楼", "桥")):
        return POIProfile(
            visit_style=POIVisitStyle.LANDMARK,
            best_time_blocks=[TimeBlockType.AFTERNOON, TimeBlockType.EVENING],
            typical_duration_minutes=60,
            intensity="light",
        )
    return POIProfile(
        visit_style=POIVisitStyle.GENERAL,
        best_time_blocks=[TimeBlockType.MORNING, TimeBlockType.AFTERNOON],
        typical_duration_minutes=DEFAULT_DURATIONS[poi_type],
        intensity="medium",
    )


def contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)


def best_place_candidate(name: str, city: str | None) -> dict | None:
    if not city:
        return None

    try:
        candidates = search_place_candidates(keyword=name, city=city, offset=8)
    except GeocodingError:
        return None

    if not candidates:
        return None

    normalized_name = name.casefold()
    ranked_candidates = sorted(
        candidates,
        key=lambda candidate: (
            candidate_name_rank(str(candidate.get("name") or "").casefold(), normalized_name),
            abs(len(str(candidate.get("name") or "")) - len(name)),
        ),
    )
    return ranked_candidates[0]


def candidate_name_rank(candidate_name: str, target_name: str) -> int:
    if candidate_name == target_name:
        return 0
    if target_name in candidate_name or candidate_name in target_name:
        return 1
    return 3


def infer_restaurant_profile_from_external(
    external_type: str,
    business_area: str,
) -> POIProfile | None:
    if not external_type:
        return None

    if contains_any(external_type, ("咖啡厅", "咖啡馆", "甜品", "冷饮", "面包甜点", "茶艺馆")):
        return POIProfile(
            visit_style=POIVisitStyle.FOOD_STOP,
            best_time_blocks=[TimeBlockType.AFTERNOON],
            typical_duration_minutes=45,
            intensity="light",
        )

    if contains_any(external_type, ("小吃", "快餐", "夜市", "美食广场")) or contains_any(
        business_area,
        ("夜", "步行街", "商圈", "里弄", "广场"),
    ):
        return POIProfile(
            visit_style=POIVisitStyle.FOOD_DISTRICT,
            best_time_blocks=[TimeBlockType.EVENING],
            typical_duration_minutes=60,
            intensity="medium",
            signal_source="external",
            signal_summary="高德类型像美食街或夜市，更适合作为晚间收口。",
        )

    if contains_any(external_type, ("火锅", "烧烤", "烤肉", "中餐厅", "特色餐饮")):
        return POIProfile(
            visit_style=POIVisitStyle.FOOD_STOP,
            best_time_blocks=[TimeBlockType.AFTERNOON, TimeBlockType.EVENING],
            typical_duration_minutes=90,
            intensity="medium",
            signal_source="external",
            signal_summary="高德类型偏正餐场景，更适合放在午后或晚餐时段。",
        )

    return POIProfile(
        visit_style=POIVisitStyle.FOOD_STOP,
        best_time_blocks=[TimeBlockType.AFTERNOON, TimeBlockType.EVENING],
        typical_duration_minutes=DEFAULT_DURATIONS[POIType.RESTAURANT],
        intensity="medium",
        signal_source="external",
        signal_summary="高德识别为餐饮地点，因此优先放在午后或晚间。",
    )


def infer_scenic_profile_from_external(
    external_type: str,
    business_area: str,
) -> POIProfile | None:
    if not external_type:
        return None

    if contains_any(external_type, ("博物馆", "美术馆", "科技馆", "展览馆", "纪念馆")):
        return POIProfile(
            visit_style=POIVisitStyle.MUSEUM,
            best_time_blocks=[TimeBlockType.MORNING, TimeBlockType.AFTERNOON],
            typical_duration_minutes=150,
            intensity="heavy",
            signal_source="external",
            signal_summary="高德识别为博物馆/展馆类地点，通常更适合白天安排。",
        )

    if contains_any(external_type, ("动物园", "海洋馆", "水族馆", "游乐园", "主题乐园")):
        return POIProfile(
            visit_style=POIVisitStyle.LANDMARK,
            best_time_blocks=[TimeBlockType.MORNING, TimeBlockType.AFTERNOON],
            typical_duration_minutes=180,
            intensity="heavy",
            signal_source="external",
            signal_summary="高德类型属于重体验景点，因此作为白天主锚点处理。",
        )

    if contains_any(external_type, ("公园", "植物园", "寺庙", "教堂", "风景名胜")):
        return POIProfile(
            visit_style=POIVisitStyle.TEMPLE_PARK,
            best_time_blocks=[TimeBlockType.MORNING, TimeBlockType.AFTERNOON],
            typical_duration_minutes=90,
            intensity="medium",
            signal_source="external",
            signal_summary="高德类型偏公园/寺庙/景区，通常更适合白天游览。",
        )

    if contains_any(external_type, ("观景台", "电视塔", "海滨浴场", "江河景观", "游船")):
        return POIProfile(
            visit_style=POIVisitStyle.NIGHT_VIEW,
            best_time_blocks=[TimeBlockType.AFTERNOON, TimeBlockType.EVENING],
            typical_duration_minutes=60,
            intensity="light",
            signal_source="external",
            signal_summary="高德类型偏观景或滨水体验，更适合下午后段或夜间。",
        )

    if contains_any(external_type, ("步行街", "特色商业街", "商圈", "购物中心")) or contains_any(
        business_area,
        ("商圈", "步行街", "天地", "广场"),
    ):
        return POIProfile(
            visit_style=POIVisitStyle.LEISURE_DISTRICT,
            best_time_blocks=[TimeBlockType.AFTERNOON, TimeBlockType.EVENING],
            typical_duration_minutes=75,
            intensity="medium",
            signal_source="external",
            signal_summary="高德类型偏休闲街区或商圈，午后到晚间体验更自然。",
        )

    if contains_any(external_type, ("古镇", "古村落", "老街", "历史建筑", "名人故居")):
        return POIProfile(
            visit_style=POIVisitStyle.OLD_STREET,
            best_time_blocks=[TimeBlockType.MORNING, TimeBlockType.AFTERNOON],
            typical_duration_minutes=90,
            intensity="medium",
            signal_source="external",
            signal_summary="高德类型偏老街或历史建筑，通常更适合白天慢逛。",
        )

    return None


def normalize_business_area(value) -> str:
    if isinstance(value, str):
        return value.casefold()
    if isinstance(value, list):
        return " ".join(str(item) for item in value).casefold()
    return ""


def normalize_city_name(city_value, province_value) -> str | None:
    if isinstance(city_value, str) and city_value.strip():
        return city_value.strip()
    if isinstance(city_value, list) and city_value:
        first_city = city_value[0]
        if isinstance(first_city, str) and first_city.strip():
            return first_city.strip()
    if isinstance(province_value, str) and province_value.strip():
        return province_value.strip()
    return None
