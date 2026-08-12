"""Deterministic external-POI boundary for browser acceptance tests only."""

from app.services import place_identity_resolution
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
        return []


place_identity_resolution.default_poi_discovery_provider = BrowserFixturePoiDiscoveryProvider


def _fixture_route(**_: object) -> dict[str, object]:
    """CI-only Amap direction boundary: stable, non-zero verified route evidence."""
    return {
        "distance_m": 1100,
        "duration_s": 840,
        "path_points": [],
        "source": "amap_fixture",
    }


from app.core import scheduler  # noqa: E402

scheduler.get_route = _fixture_route

from app.main import app  # noqa: E402
