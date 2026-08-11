from __future__ import annotations

from typing import Any

import requests

from .models import PlaceBusiness


class GooglePlacesClient:
    BASE_URL = "https://places.googleapis.com/v1/places:searchText"
    FIELD_MASK = ",".join(
        (
            "places.id",
            "places.displayName",
            "places.formattedAddress",
            "places.websiteUri",
            "places.googleMapsUri",
            "places.nationalPhoneNumber",
            "places.rating",
            "places.userRatingCount",
            "places.businessStatus",
            "places.types",
            "places.primaryType",
            "nextPageToken",
        )
    )

    def __init__(
        self, api_key: str, session: requests.Session | None = None
    ) -> None:
        self.api_key = api_key
        self.session = session or requests.Session()

    def search(
        self,
        query: str,
        *,
        page_size: int = 20,
        max_pages: int = 1,
        language_code: str = "en-GB",
        region_code: str = "GB",
    ) -> list[PlaceBusiness]:
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": self.FIELD_MASK,
        }
        page_token = ""
        found: list[PlaceBusiness] = []
        for _ in range(max(1, max_pages)):
            payload: dict[str, Any] = {
                "textQuery": query,
                "pageSize": min(max(1, page_size), 20),
                "languageCode": language_code,
                "regionCode": region_code,
            }
            if page_token:
                payload["pageToken"] = page_token
            response = self.session.post(
                self.BASE_URL,
                headers=headers,
                json=payload,
                timeout=45,
            )
            response.raise_for_status()
            data = response.json()
            found.extend(self._to_place(item) for item in data.get("places", []))
            page_token = str(data.get("nextPageToken") or "")
            if not page_token:
                break
        return found

    def search_queries(
        self,
        queries: list[str],
        *,
        page_size: int = 20,
        max_pages_per_query: int = 1,
    ) -> list[PlaceBusiness]:
        unique: dict[str, PlaceBusiness] = {}
        for query in queries:
            for place in self.search(
                query,
                page_size=page_size,
                max_pages=max_pages_per_query,
            ):
                unique.setdefault(place.place_id, place)
        return list(unique.values())

    @staticmethod
    def _to_place(item: dict[str, Any]) -> PlaceBusiness:
        display_name = item.get("displayName") or {}
        return PlaceBusiness(
            place_id=str(item.get("id") or ""),
            name=str(display_name.get("text") or "").strip(),
            formatted_address=str(item.get("formattedAddress") or "").strip(),
            website=str(item.get("websiteUri") or "").strip(),
            google_maps_url=str(item.get("googleMapsUri") or "").strip(),
            phone=str(item.get("nationalPhoneNumber") or "").strip(),
            rating=(float(item["rating"]) if item.get("rating") is not None else None),
            review_count=int(item.get("userRatingCount") or 0),
            business_status=str(item.get("businessStatus") or ""),
            types=[str(value) for value in item.get("types", [])],
        )
