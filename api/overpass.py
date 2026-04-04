"""
Local POI Dataset Client (Replacing Live Overpass API)
======================================================
Queries for Points of Interest (POIs) using a pre-calculated dataset
to completely avoid '429 Too Many Requests' rate limits from public servers.
"""

import os
import json
import math

class OverpassClient:
    def __init__(self, cache):
        self.cache = cache
        self.dataset = self._load_dataset()

    def _load_dataset(self):
        """Loads the pre-calculated POI JSON dataset into memory."""
        try:
            base_dir = os.path.dirname(os.path.dirname(__file__))
            dataset_path = os.path.join(base_dir, 'src', 'data', 'poi-dataset.json')
            with open(dataset_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"[Dataset] Failed to load POI dataset: {e}")
            return []

    def _haversine(self, lat1, lon1, lat2, lon2):
        """Calculate distance in km."""
        R = 6371
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (math.sin(dlat / 2) * math.sin(dlat / 2) +
             math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
             math.sin(dlon / 2) * math.sin(dlon / 2))
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return R * c

    def get_cached_pois(self, lat, lng, radius_m=25000):
        """Bypass caching entirely because reading from memory is instant."""
        return None

    def get_pois(self, lat, lng, radius_m=25000):
        """
        Get POIs near a location from the static dataset.
        Returns the closest matching city's pre-calculated metadata.
        """
        if not self.dataset:
            return {"data": self._default_pois(), "source": "DEFAULT"}

        # Find the closest city in our dataset
        best_match = None
        min_dist = float('inf')
        
        for data in self.dataset:
            dist = self._haversine(lat, lng, data["lat"], data["lng"])
            if dist < min_dist:
                min_dist = dist
                best_match = data
                
        if best_match and min_dist < 50:  # Within 50km
            return {"data": best_match, "source": "LOCAL_DATASET"}
            
        print(f"[Dataset] No close match found for {lat}, {lng}. Using default.")
        return {"data": self._default_pois(), "source": "DEFAULT"}

    @staticmethod
    def _default_pois():
        """Default POI data when everything fails."""
        return {
            "osmChargers": 0,
            "fuelStations": 3,
            "malls": 1,
            "parkingLots": 2,
            "highwaySegments": 1,
            "hasHighwayAccess": True,
            "totalPOIs": 6,
            "coLocationScore": 5,
        }
