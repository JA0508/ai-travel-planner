"""Deterministic external-POI boundary for browser acceptance tests only."""

from app.services import place_identity_resolution
from app.schemas import VerifiedPlaceRef
from app.services.poi_discovery_provider import PoiDiscoveryCandidate, PoiDiscoveryCapability


class BrowserFixturePoiDiscoveryProvider:
    """A bounded provider substitute so CI never needs a live Amap credential."""

    _CANDIDATES = {
        "西湖": PoiDiscoveryCandidate(
            name="西湖风景名胜区",
            address="杭州市西湖区",
            type="风景名胜",
            typecode="110000",
            business_area="杭州",
            latitude=30.235,
            longitude=120.148,
            provider_place_id="fixture-west-lake",
        ),
        "灵隐寺": PoiDiscoveryCandidate(
            name="灵隐寺",
            address="杭州市西湖区灵隐路法云弄1号",
            type="风景名胜",
            typecode="110000",
            business_area="杭州",
            latitude=30.240,
            longitude=120.102,
            provider_place_id="fixture-lingyin-temple",
        ),
        "龙井村": PoiDiscoveryCandidate(
            name="龙井村",
            address="杭州市西湖区龙井路",
            type="风景名胜",
            typecode="110000",
            business_area="杭州",
            latitude=30.216,
            longitude=120.112,
            provider_place_id="fixture-longjing-village",
        ),
        "中国茶叶博物馆": PoiDiscoveryCandidate(
            name="中国茶叶博物馆（双峰馆区）",
            address="杭州市西湖区龙井路88号",
            type="博物馆",
            typecode="140100",
            business_area="杭州",
            latitude=30.218,
            longitude=120.104,
            provider_place_id="fixture-china-tea-museum",
        ),
        "上海博物馆": PoiDiscoveryCandidate(
            name="上海博物馆（人民广场馆）",
            address="上海市黄浦区人民大道201号",
            type="博物馆",
            typecode="140100",
            business_area="上海",
            latitude=31.230,
            longitude=121.473,
            provider_place_id="fixture-shanghai-museum",
        ),
        "龙井村茶歇": PoiDiscoveryCandidate(
            name="龙井村茶歇",
            address="杭州市西湖区龙井路",
            type="中餐厅",
            typecode="050100",
            business_area="杭州",
            latitude=30.21829,
            longitude=120.10924,
            provider_place_id="fixture-longjing-tea-stop",
        ),
        "河坊街小吃街": PoiDiscoveryCandidate(
            name="河坊街小吃街",
            address="杭州市上城区河坊街",
            type="特色餐食",
            typecode="050100",
            business_area="杭州",
            latitude=30.24204,
            longitude=120.17331,
            provider_place_id="fixture-hefang-food-street",
        ),
        "湖滨银泰夜景": PoiDiscoveryCandidate(
            name="湖滨银泰夜景",
            address="杭州市上城区湖滨",
            type="餐饮服务",
            typecode="050100",
            business_area="杭州",
            latitude=30.25739,
            longitude=120.16089,
            provider_place_id="fixture-hubin-dinner",
        ),
        "武林夜市": PoiDiscoveryCandidate(
            name="武林夜市",
            address="杭州市拱墅区武林路",
            type="特色餐食",
            typecode="050100",
            business_area="杭州",
            latitude=30.27431,
            longitude=120.16548,
            provider_place_id="fixture-wulin-night-market",
        ),
        "青芝坞餐厅": PoiDiscoveryCandidate(
            name="青芝坞餐厅",
            address="杭州市西湖区青芝坞",
            type="中餐厅",
            typecode="050100",
            business_area="杭州",
            latitude=30.26049,
            longitude=120.12745,
            provider_place_id="fixture-qingzhiwu",
        ),
        "满觉陇茶歇": PoiDiscoveryCandidate(
            name="满觉陇茶歇",
            address="杭州市西湖区满觉陇",
            type="中餐厅",
            typecode="050100",
            business_area="杭州",
            latitude=30.21477,
            longitude=120.11953,
            provider_place_id="fixture-manjuelong-tea-stop",
        ),
        "茶人村": PoiDiscoveryCandidate(
            name="茶人村",
            address="杭州市西湖区龙井路",
            type="杭帮菜",
            typecode="050100",
            business_area="杭州",
            latitude=30.229,
            longitude=120.111,
            provider_place_id="fixture-tea-village",
        ),
        "龙井草堂": PoiDiscoveryCandidate(
            name="龙井草堂",
            address="杭州市西湖区龙井路",
            type="杭帮菜",
            typecode="050100",
            business_area="杭州",
            latitude=30.226,
            longitude=120.109,
            provider_place_id="fixture-longjing-cottage",
        ),
        "远山宴": PoiDiscoveryCandidate(
            name="远山宴",
            address="杭州市临安区",
            type="中餐厅",
            typecode="050100",
            business_area="杭州",
            latitude=30.5,
            longitude=119.7,
            provider_place_id="fixture-far-dinner",
        ),
    }

    def capability(self) -> PoiDiscoveryCapability:
        return PoiDiscoveryCapability(
            provider="amap",
            app_env="test",
            mode="required",
            required=True,
            poi_discovery_enabled=True,
            text_search_enabled=True,
            around_search_enabled=True,
            catalog_fallback_enabled=False,
            missing_config=(),
            production_ready=True,
        )

    def search_text(self, *, keyword: str, city: str, offset: int) -> list[PoiDiscoveryCandidate]:
        candidate = self._CANDIDATES.get(keyword.strip())
        return [candidate] if candidate and candidate.business_area == city.strip() else []

    def search_around(self, **_: object) -> list[PoiDiscoveryCandidate]:
        return [
            self._CANDIDATES["青芝坞餐厅"],
            self._CANDIDATES["茶人村"],
            self._CANDIDATES["龙井草堂"],
            self._CANDIDATES["远山宴"],
        ]


place_identity_resolution.default_poi_discovery_provider = BrowserFixturePoiDiscoveryProvider


def _fixture_route(**_: object) -> dict[str, object]:
    """Shared browser-planning route: preserve the established golden-path evidence."""
    return {
        "distance_m": 1100,
        "duration_s": 840,
        "path_points": [],
        "source": "amap_fixture",
    }


def _fixture_replacement_route(
    *,
    origin_lat: float,
    origin_lng: float,
    dest_lat: float,
    dest_lng: float,
    **_: object,
) -> dict[str, object]:
    """Replacement-only routes distinguish safe nearby options from unsafe ones."""
    del origin_lng, dest_lng
    unsafe = origin_lat >= 30.4 or dest_lat >= 30.4
    return {
        "distance_m": 8000 if unsafe else 800,
        "duration_s": 9000 if unsafe else 600,
        "path_points": [],
        "source": "amap_fixture",
    }


from app.core import scheduler  # noqa: E402

scheduler.get_route = _fixture_route

from app.main import app  # noqa: E402

from app.api.routes import itinerary as itinerary_routes  # noqa: E402
from app.services import itinerary_completion_recommendation  # noqa: E402
from app.trips import service as trip_service  # noqa: E402

itinerary_completion_recommendation.default_poi_discovery_provider = (
    BrowserFixturePoiDiscoveryProvider
)
itinerary_completion_recommendation.get_walking_route = _fixture_replacement_route
trip_service.default_poi_discovery_provider = BrowserFixturePoiDiscoveryProvider

_production_bootstrap = itinerary_routes.build_sparse_city_bootstrap_pois


def _fixture_verified_bootstrap(**kwargs):
    scenic, restaurants = _production_bootstrap(**kwargs)
    provider = BrowserFixturePoiDiscoveryProvider()

    def attach_identity(poi):
        candidate = provider._CANDIDATES.get(poi.name)
        if candidate is None or candidate.provider_place_id is None:
            return poi
        verified = VerifiedPlaceRef(
            stable_id=f"amap:{candidate.provider_place_id}",
            original_name=candidate.name,
            canonical_name=candidate.name,
            provider="amap",
            provider_place_id=candidate.provider_place_id,
            latitude=float(candidate.latitude),
            longitude=float(candidate.longitude),
            category=candidate.type,
        )
        return poi.model_copy(
            update={
                "canonical_place_id": candidate.provider_place_id,
                "verified_place": verified,
            },
            deep=True,
        )

    return [attach_identity(poi) for poi in scenic], [attach_identity(poi) for poi in restaurants]


itinerary_routes.build_sparse_city_bootstrap_pois = _fixture_verified_bootstrap
