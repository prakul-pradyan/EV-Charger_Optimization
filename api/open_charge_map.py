"""
Open Charge Map API Client
===========================
Proxies requests to the OCM API with caching.
Falls back to a curated dataset of 105 Indian charger locations
when the API returns 403 (no API key) or empty results.
Rate-limited to 1 request per second.
"""

import os
import json
import time
import requests

OCM_BASE = "https://api.openchargemap.io/v3/poi/"
OCM_API_KEY = ""
RATE_LIMIT_INTERVAL = 1.1  # seconds between requests

# Fallback data path
FALLBACK_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "src", "data", "chargers-fallback.json",
)


class OpenChargeMapClient:
    def __init__(self, cache):
        self.cache = cache
        self._last_request_time = 0
        self._fallback_data = None

    def _load_fallback(self):
        """Load the curated fallback charger dataset."""
        if self._fallback_data is None:
            try:
                with open(FALLBACK_PATH, "r", encoding="utf-8") as f:
                    self._fallback_data = json.load(f)
                print(f"[OCM] Loaded fallback dataset: {len(self._fallback_data)} chargers")
            except (FileNotFoundError, json.JSONDecodeError) as e:
                print(f"[OCM] Fallback load failed: {e}")
                self._fallback_data = []
        return self._fallback_data

    def _rate_limit(self):
        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < RATE_LIMIT_INTERVAL:
            time.sleep(RATE_LIMIT_INTERVAL - elapsed)
        self._last_request_time = time.time()

    def _fetch(self, params):
        """Make a rate-limited request to the OCM API."""
        self._rate_limit()
        try:
            resp = requests.get(
                OCM_BASE,
                params=params,
                timeout=30,
                headers={
                    "User-Agent": "EVChargerOptimisation/1.0",
                    "X-API-Key": OCM_API_KEY,
                },
            )
            if resp.status_code == 403:
                print("[OCM] API returned 403 (API key required). Using fallback dataset.")
                return None  # Signal to use fallback
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list) and len(data) > 0:
                return data
            print("[OCM] API returned empty results. Using fallback dataset.")
            return None
        except requests.RequestException as e:
            print(f"[OCM] Request failed: {e}. Using fallback dataset.")
            return None

    def get_nearby(self, lat, lng, radius_km=10, max_results=100):
        """Get chargers near a location within radius_km."""
        cache_params = {"lat": round(lat, 3), "lng": round(lng, 3), "r": radius_km}

        # Try cache first (fresh only for nearby queries)
        cached, tier = self.cache.get_fresh("ocm_nearby", cache_params, ttl=43200)
        if cached is not None and len(cached) > 0:
            return {"data": cached, "source": tier, "count": len(cached)}

        # Fetch from API
        raw = self._fetch(
            {
                "output": "json",
                "countrycode": "IN",
                "latitude": lat,
                "longitude": lng,
                "distance": radius_km,
                "distanceunit": "km",
                "maxresults": max_results,
                "compact": "true",
                "verbose": "false",
            }
        )

        # If API failed or returned empty, filter fallback by distance
        if raw is None:
            from engine.scoring_engine import haversine
            fallback = self._load_fallback()
            chargers = [
                c for c in fallback
                if haversine(lat, lng, c["lat"], c["lng"]) <= radius_km
            ]
            self.cache.set("ocm_nearby", cache_params, chargers, ttl=43200)
            return {"data": chargers, "source": "FALLBACK", "count": len(chargers)}

        # Extract relevant fields from API response
        chargers = []
        for item in raw:
            addr = item.get("AddressInfo", {})
            chargers.append(
                {
                    "id": item.get("ID"),
                    "lat": addr.get("Latitude"),
                    "lng": addr.get("Longitude"),
                    "town": addr.get("Town", ""),
                    "state": addr.get("StateOrProvince", ""),
                    "powerKW": self._extract_power(item),
                    "numPoints": item.get("NumberOfPoints", 1),
                    "operator": (item.get("OperatorInfo") or {}).get("Title", "Unknown"),
                    "usageType": (item.get("UsageType") or {}).get("Title", "Unknown"),
                    "statusType": (item.get("StatusType") or {}).get("Title", "Unknown"),
                    "isOperational": (item.get("StatusType") or {}).get("IsOperational", False),
                }
            )

        self.cache.set("ocm_nearby", cache_params, chargers, ttl=43200)
        return {"data": chargers, "source": "API", "count": len(chargers)}

    def get_all_india(self):
        """Get all chargers in India. Heavily cached (48h)."""
        cache_params = {"country": "IN", "scope": "all_v2"}

        cached, tier = self.cache.get("ocm_all_india", cache_params, ttl=172800)
        if cached is not None and len(cached) > 0:
            return {"data": cached, "source": tier, "count": len(cached)}

        # Fetch from API
        raw = self._fetch(
            {
                "output": "json",
                "countrycode": "IN",
                "maxresults": 10000,
                "compact": "true",
                "verbose": "false",
            }
        )

        # If API failed, use fallback
        if raw is None:
            fallback = self._load_fallback()
            self.cache.set("ocm_all_india", cache_params, fallback, ttl=172800)
            return {"data": fallback, "source": "FALLBACK", "count": len(fallback)}

        all_chargers = []
        for item in raw:
            addr = item.get("AddressInfo", {})
            all_chargers.append(
                {
                    "id": item.get("ID"),
                    "lat": addr.get("Latitude"),
                    "lng": addr.get("Longitude"),
                    "town": addr.get("Town", ""),
                    "state": addr.get("StateOrProvince", ""),
                    "powerKW": self._extract_power(item),
                    "numPoints": item.get("NumberOfPoints", 1),
                    "operator": (item.get("OperatorInfo") or {}).get("Title", "Unknown"),
                    "isOperational": (item.get("StatusType") or {}).get("IsOperational", False),
                }
            )

        self.cache.set("ocm_all_india", cache_params, all_chargers, ttl=172800)
        return {"data": all_chargers, "source": "API", "count": len(all_chargers)}

    @staticmethod
    def _extract_power(item):
        """Extract max power output in kW from a charger entry."""
        connections = item.get("Connections") or []
        max_power = 0
        for conn in connections:
            power = conn.get("PowerKW") or 0
            if power > max_power:
                max_power = power
        return max_power
