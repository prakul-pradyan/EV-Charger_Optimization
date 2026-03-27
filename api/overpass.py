"""
Overpass API Client (OpenStreetMap)
====================================
Queries for Points of Interest near candidate locations:
  - Fuel stations (potential co-location)
  - Shopping malls / parking lots (high footfall)
  - Highway proximity (trunk roads, motorways)
"""

import time
import requests

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
RATE_LIMIT_INTERVAL = 2.0  # Overpass is stricter on rate-limiting


class OverpassClient:
    def __init__(self, cache):
        self.cache = cache
        self._last_request_time = 0

    def _rate_limit(self):
        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < RATE_LIMIT_INTERVAL:
            time.sleep(RATE_LIMIT_INTERVAL - elapsed)
        self._last_request_time = time.time()

    def get_cached_pois(self, lat, lng, radius_m=25000):
        """Check if POIs for this location are already cached. Returns data or None."""
        cache_params = {"lat": round(lat, 2), "lng": round(lng, 2), "r": radius_m}
        cached, tier = self.cache.get("overpass_pois", cache_params, ttl=604800)
        if cached is not None:
            return {"data": cached, "source": tier}
        return None

    def get_pois(self, lat, lng, radius_m=25000):
        """
        Get POIs near a location.
        Returns counts and locations of fuel stations, malls, parking, highways.
        """
        cache_params = {"lat": round(lat, 2), "lng": round(lng, 2), "r": radius_m}
        cached, tier = self.cache.get("overpass_pois", cache_params, ttl=604800)  # 7 days
        if cached is not None:
            return {"data": cached, "source": tier}

        query = f"""
        [out:json][timeout:25];
        (
          node["amenity"="fuel"](around:{radius_m},{lat},{lng});
          node["shop"="mall"](around:{radius_m},{lat},{lng});
          way["shop"="mall"](around:{radius_m},{lat},{lng});
          node["amenity"="parking"](around:{radius_m},{lat},{lng});
          way["amenity"="parking"](around:{radius_m},{lat},{lng});
          way["highway"~"trunk|motorway"](around:{radius_m},{lat},{lng});
        );
        out center count;
        """

        self._rate_limit()
        try:
            resp = requests.post(
                OVERPASS_URL,
                data={"data": query},
                timeout=30,
                headers={"User-Agent": "EVChargerOptimisation/1.0"},
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            print(f"[Overpass] Request failed: {e}")
            # Return defaults on failure
            result = self._default_pois()
            return {"data": result, "source": "DEFAULT"}

        result = self._parse_pois(data, lat, lng)
        self.cache.set("overpass_pois", cache_params, result, ttl=604800)
        return {"data": result, "source": "API"}

    def _parse_pois(self, data, center_lat, center_lng):
        """Parse Overpass response into structured POI data."""
        fuel_stations = 0
        malls = 0
        parking_lots = 0
        highway_segments = 0

        elements = data.get("elements", [])
        for el in elements:
            tags = el.get("tags", {})
            if tags.get("amenity") == "fuel":
                fuel_stations += 1
            elif tags.get("shop") == "mall":
                malls += 1
            elif tags.get("amenity") == "parking":
                parking_lots += 1
            elif tags.get("highway") in ("trunk", "motorway"):
                highway_segments += 1

        return {
            "fuelStations": fuel_stations,
            "malls": malls,
            "parkingLots": parking_lots,
            "highwaySegments": highway_segments,
            "hasHighwayAccess": highway_segments > 0,
            "totalPOIs": fuel_stations + malls + parking_lots,
            "coLocationScore": min(10, fuel_stations * 2 + malls * 3 + parking_lots),
        }

    @staticmethod
    def _default_pois():
        """Default POI data when API fails."""
        return {
            "fuelStations": 3,
            "malls": 1,
            "parkingLots": 2,
            "highwaySegments": 1,
            "hasHighwayAccess": True,
            "totalPOIs": 6,
            "coLocationScore": 5,
        }
