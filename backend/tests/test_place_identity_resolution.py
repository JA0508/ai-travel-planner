from __future__ import annotations

import unittest

from app.services.place_identity_resolution import (
    PlaceIdentityResolutionError,
    confirm_place_identity,
    discover_place_identities,
    search_place_identity_suggestions,
)
from app.services.poi_discovery_provider import PoiDiscoveryCandidate, PoiDiscoveryCapability, PoiDiscoveryUnavailable


class StaticPoiProvider:
    def capability(self) -> PoiDiscoveryCapability:
        return PoiDiscoveryCapability(
            provider="amap", app_env="test", mode="required", required=True,
            poi_discovery_enabled=True, text_search_enabled=True, around_search_enabled=True,
            catalog_fallback_enabled=False, missing_config=(), production_ready=True,
        )

    def search_text(self, *, keyword: str, city: str, offset: int) -> list[PoiDiscoveryCandidate]:
        return [
            PoiDiscoveryCandidate(
                name="西湖风景名胜区", address="杭州市西湖区", type="风景名胜", typecode="110000",
                business_area="杭州", latitude=30.235, longitude=120.148, provider_place_id="amap-west-lake",
            ),
            PoiDiscoveryCandidate(
                name="西湖音乐喷泉", address="杭州市上城区", type="风景名胜", typecode="110000",
                business_area="杭州", latitude=30.251, longitude=120.164, provider_place_id="amap-fountain",
            ),
        ][:offset]

    def search_around(self, **_: object) -> list[PoiDiscoveryCandidate]:
        return []


class PlaceIdentityResolutionTests(unittest.TestCase):
    def test_destination_duration_phrase_is_not_a_fake_poi(self) -> None:
        identities = discover_place_identities(
            direct_user_text="我想去西安玩两天。",
            city="西安",
            provider=StaticPoiProvider(),
        )
        self.assertEqual(identities, [])

    def test_discovery_never_silently_promotes_direct_must_visit_place(self) -> None:
        identities = discover_place_identities(
            direct_user_text="我想去杭州玩两天，已经想去西湖。",
            city="杭州",
            provider=StaticPoiProvider(),
        )
        west_lake = next(item for item in identities if item.original_name == "西湖")
        self.assertEqual(west_lake.ownership, "must")
        self.assertEqual(west_lake.resolution_status, "ambiguous")
        self.assertEqual([item.provider_place_id for item in west_lake.confirmation_options], ["amap-west-lake", "amap-fountain"])
        self.assertIsNone(west_lake.latitude)

    def test_discovery_preserves_explicit_places_when_legacy_compiler_limit_is_exceeded(self) -> None:
        identities = discover_place_identities(
            direct_user_text=(
                "我想去重庆玩 3 天。已经确定想去洪崖洞、解放碑、李子坝轻轨站、鹅岭二厂、"
                "山城步道、南山一棵树观景台、磁器口、长江索道、罗汉寺。"
                "请按 Day 1 / Day 2 / Day 3 输出，每个地点说明推荐原因、预计停留时长、与下一站的交通方式。"
            ),
            city="重庆",
            provider=StaticPoiProvider(),
        )

        self.assertEqual(
            [identity.original_name for identity in identities],
            [
                "洪崖洞",
                "解放碑",
                "李子坝轻轨站",
                "鹅岭二厂",
                "山城步道",
                "南山一棵树观景台",
                "磁器口",
                "长江索道",
                "罗汉寺",
            ],
        )
        self.assertTrue(all(identity.ownership == "must" for identity in identities))

    def test_confirm_rehydrates_provider_identity_not_client_geometry(self) -> None:
        identity = discover_place_identities(
            direct_user_text="我想去杭州玩两天，已经想去西湖。",
            city="杭州",
            provider=StaticPoiProvider(),
        )[0]
        confirmed = confirm_place_identity(
            identity=identity,
            provider_place_id="amap-west-lake",
            provider=StaticPoiProvider(),
        )
        self.assertEqual(confirmed.resolution_status, "verified")
        self.assertEqual(confirmed.provider, "amap")
        self.assertEqual(confirmed.provider_place_id, "amap-west-lake")
        self.assertEqual((confirmed.latitude, confirmed.longitude), (30.235, 120.148))
        self.assertEqual(confirmed.confirmation_options, [])

    def test_unknown_provider_selection_is_rejected(self) -> None:
        identity = discover_place_identities(
            direct_user_text="我想去杭州玩两天，已经想去西湖。",
            city="杭州",
            provider=StaticPoiProvider(),
        )[0]
        with self.assertRaisesRegex(PlaceIdentityResolutionError, "place_identity_selection_not_found"):
            confirm_place_identity(
                identity=identity,
                provider_place_id="tampered-browser-id",
                provider=StaticPoiProvider(),
            )

    def test_manual_search_ranks_a_provider_suggestion_without_confirming_it(self) -> None:
        class QueryAwareProvider(StaticPoiProvider):
            def search_text(self, *, keyword: str, city: str, offset: int) -> list[PoiDiscoveryCandidate]:
                if keyword == "十八梯":
                    return [
                        PoiDiscoveryCandidate(
                            name="十八梯传统风貌区", address="重庆市渝中区十八梯", type="风景名胜", typecode="110000",
                            business_area="重庆", latitude=29.553, longitude=106.574, provider_place_id="amap-shibati",
                        ),
                        PoiDiscoveryCandidate(
                            name="重庆十八梯", address="重庆市渝中区", type="商圈", typecode="060000",
                            business_area="重庆", latitude=29.554, longitude=106.575, provider_place_id="amap-shibati-nearby",
                        ),
                    ]
                return super().search_text(keyword=keyword, city=city, offset=offset)

        identity = discover_place_identities(
            direct_user_text="我想去重庆玩三天，已经想去山城步道。",
            city="重庆",
            provider=QueryAwareProvider(),
        )[0]

        suggestions = search_place_identity_suggestions(
            identity=identity,
            query="十八梯",
            provider=QueryAwareProvider(),
        )

        self.assertEqual(suggestions.query, "十八梯")
        self.assertEqual(suggestions.recommended_provider_place_id, "amap-shibati")
        self.assertEqual([item.provider_place_id for item in suggestions.options], ["amap-shibati", "amap-shibati-nearby"])
        self.assertEqual(identity.resolution_status, "ambiguous")

        confirmed = confirm_place_identity(
            identity=identity,
            provider_place_id="amap-shibati",
            search_query="十八梯",
            provider=QueryAwareProvider(),
        )
        self.assertEqual(confirmed.canonical_name, "十八梯传统风貌区")
        self.assertEqual(confirmed.provider_place_id, "amap-shibati")

    def test_manual_search_does_not_misrepresent_provider_outage_as_no_candidates(self) -> None:
        identity = discover_place_identities(
            direct_user_text="我想去杭州玩两天，已经想去西湖。",
            city="杭州",
            provider=StaticPoiProvider(),
        )[0]

        class UnavailableProvider(StaticPoiProvider):
            def search_text(self, *, keyword: str, city: str, offset: int) -> list[PoiDiscoveryCandidate]:
                raise PoiDiscoveryUnavailable("provider timeout")

        with self.assertRaisesRegex(PlaceIdentityResolutionError, "place_identity_provider_unavailable"):
            search_place_identity_suggestions(
                identity=identity,
                query="西湖",
                provider=UnavailableProvider(),
            )
