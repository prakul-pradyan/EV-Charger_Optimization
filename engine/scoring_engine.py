"""
Scoring Engine
===============
Computes a composite score (0–100) for each candidate location.

Sub-scores and default weights:
  Demand Score         (30%) — EV registrations in region, population, growth
  Competition Score    (25%) — Inverse of existing charger density in radius
  Accessibility Score  (20%) — Highway access + urban POI proximity
  Grid Score           (15%) — Power reliability, tariff competitiveness
  Commercial Viability (10%) — Co-location opportunities (malls, fuel stations)
"""

import math
from collections import defaultdict

# Pre-compute constants
_R = 6371  # Earth radius in km
_DEG_TO_RAD = math.pi / 180.0
# Grid cells for spatial index: 0.25° ≈ 28 km
_GRID_CELL_SIZE = 0.25


def haversine(lat1, lng1, lat2, lng2):
    """Distance in km between two lat/lng points."""
    dlat = (lat2 - lat1) * _DEG_TO_RAD
    dlng = (lng2 - lng1) * _DEG_TO_RAD
    a = (
        math.sin(dlat * 0.5) ** 2
        + math.cos(lat1 * _DEG_TO_RAD)
        * math.cos(lat2 * _DEG_TO_RAD)
        * math.sin(dlng * 0.5) ** 2
    )
    return _R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _build_charger_grid(charger_list):
    """Build a spatial grid index for O(1) lookups of nearby chargers."""
    grid = defaultdict(list)
    for c in charger_list:
        clat = c.get("lat")
        clng = c.get("lng")
        if clat is not None and clng is not None:
            cell = (int(clat / _GRID_CELL_SIZE), int(clng / _GRID_CELL_SIZE))
            grid[cell].append(c)
    return grid


def _get_nearby_chargers(lat, lng, grid, radius_km=25):
    """Get chargers within radius_km using the spatial grid index."""
    cell_radius = max(1, int(math.ceil(radius_km / (111.0 * _GRID_CELL_SIZE))))
    center_cell_lat = int(lat / _GRID_CELL_SIZE)
    center_cell_lng = int(lng / _GRID_CELL_SIZE)

    nearby = []
    for dlat in range(-cell_radius, cell_radius + 1):
        for dlng in range(-cell_radius, cell_radius + 1):
            cell = (center_cell_lat + dlat, center_cell_lng + dlng)
            for c in grid.get(cell, []):
                if haversine(lat, lng, c["lat"], c["lng"]) <= radius_km:
                    nearby.append(c)
    return nearby


class ScoringEngine:
    DEFAULT_WEIGHTS = {
        "demand": 0.30,
        "competition": 0.25,
        "accessibility": 0.20,
        "grid": 0.15,
        "commercial": 0.10,
    }

    # Tier-based search radius: metros need wider radius, small cities smaller
    TIER_RADIUS_KM = {1: 25, 2: 15, 3: 10}

    def score_all(self, cities, ev_data, grid_data, chargers, pois, weight_overrides=None):
        """
        Score all candidate cities and return sorted list (best first).
        """
        weights = {**self.DEFAULT_WEIGHTS, **(weight_overrides or {})}

        # Pre-process: build state lookup tables
        state_ev = {s["state"]: s for s in ev_data.get("states", [])}
        state_grid = {r["state"]: r for r in grid_data.get("regions", [])}
        charger_list = chargers.get("data", []) if isinstance(chargers, dict) else chargers

        # Build spatial index for chargers (O(N) once, then O(~1) per city lookup)
        charger_grid = _build_charger_grid(charger_list)

        # Compute raw scores for normalization
        raw_scores = []
        for city in cities:
            raw = self._compute_raw(city, state_ev, state_grid, charger_grid, pois)
            raw_scores.append((city, raw))

        # Normalize each sub-score to 0–100
        score_keys = ["demand", "competition", "accessibility", "grid", "commercial"]
        mins = {}
        maxs = {}
        for key in score_keys:
            values = [r[key] for _, r in raw_scores]
            mins[key] = min(values) if values else 0
            maxs[key] = max(values) if values else 1

        results = []
        for city, raw in raw_scores:
            normalized = {}
            for key in score_keys:
                spread = maxs[key] - mins[key]
                if spread > 0:
                    normalized[key] = ((raw[key] - mins[key]) / spread) * 100
                else:
                    normalized[key] = 50  # All equal → mid-range

            composite = sum(normalized[k] * weights[k] for k in score_keys)

            results.append(
                {
                    "rank": 0,  # filled after sort
                    "city": city["city"],
                    "state": city["state"],
                    "lat": city["lat"],
                    "lng": city["lng"],
                    "population": city.get("population", 0),
                    "tier": city.get("tier", 2),
                    "compositeScore": round(composite, 2),
                    "scores": {k: round(normalized[k], 2) for k in score_keys},
                    "raw": {k: round(raw[k], 4) for k in score_keys},
                    "chargersInRadius": raw.get("charger_count", 0),
                    "searchRadiusKm": raw.get("search_radius_km", 25),
                    "chargerToVehicleRatio": raw.get("charger_to_vehicle", 0),
                    "accessibilityLabel": self._accessibility_label(normalized["accessibility"]),
                }
            )

        # Sort by composite score descending
        results.sort(key=lambda x: x["compositeScore"], reverse=True)
        for i, r in enumerate(results):
            r["rank"] = i + 1

        return results

    def _compute_raw(self, city, state_ev, state_grid, charger_grid, pois):
        """Compute raw (unnormalized) sub-scores for a single city."""
        state = city["state"]
        ev = state_ev.get(state, {})
        grid = state_grid.get(state, {})
        lat, lng = city["lat"], city["lng"]
        pop = city.get("population", 500000)
        tier = city.get("tier", 2)

        # Tier-based search radius
        search_radius = self.TIER_RADIUS_KM.get(tier, 15)

        # ── Demand Score ──
        ev_regs = ev.get("evRegistrations", 10000)
        growth = ev.get("growthRate", 15) / 100
        penetration = ev.get("evPenetration", 5) / 100
        state_pop = ev.get("population", 50000000)
        # City's share of state registrations (proportional to population)
        city_ev_share = (pop / max(state_pop, 1)) * ev_regs
        demand = (city_ev_share * (1 + growth)) + (pop * penetration * 0.001)

        # Extract city's specific POI data from the batch dictionary
        poi_key = f"{lat}_{lng}"
        poi_data = pois.get(poi_key, {})
        if isinstance(poi_data, dict) and "data" in poi_data:
            poi_data = poi_data["data"]
        if not isinstance(poi_data, dict):
            poi_data = {}

        # ── Competition Score ──
        # Count existing chargers within the tier-appropriate radius
        nearby = _get_nearby_chargers(lat, lng, charger_grid, radius_km=search_radius)
        ocm_count = sum(c.get("numPoints", 1) for c in nearby)
        osm_count = poi_data.get("osmChargers", 0)
        charger_count = ocm_count + osm_count

        # Competition scoring: scaling thresholds by market size
        # With OSM + OCM data, numbers will be more realistic
        if charger_count < 2:
            competition = 60  # Severely undersupplied/unproven
        elif charger_count <= 25:
            competition = 90  # Sweet spot: proven demand, plenty of room
        elif charger_count <= 75:
            # Scale smoothly from 90 down to 40
            pct = (charger_count - 25) / 50.0
            competition = 90 - (pct * 50)
        else:
            competition = max(20, 40 - (charger_count - 75) * 0.5)

        # Charger-to-vehicle ratio
        charger_to_vehicle = round(charger_count / max(city_ev_share, 1), 6)

        # ── Accessibility Score ──

        has_highway = poi_data.get("hasHighwayAccess", city.get("nhConnectivity", False))
        total_pois = poi_data.get("totalPOIs", 5)
        accessibility = (30 if has_highway else 0) + min(70, total_pois * 7)

        # ── Grid Score ──
        reliability = grid.get("gridReliability", 6)
        tariff = grid.get("avgTariffPerKwh", 6)
        # Lower tariff = better (invert: 10 - tariff normalised)
        tariff_score = max(0, (10 - tariff)) * 10
        grid_score = reliability * 7 + tariff_score * 0.3

        # ── Commercial Viability ──
        co_location = poi_data.get("coLocationScore", 5)
        tier_bonus = {1: 20, 2: 10, 3: 0}.get(tier, 0)
        commercial = co_location * 8 + tier_bonus

        return {
            "demand": demand,
            "competition": competition,
            "accessibility": accessibility,
            "grid": grid_score,
            "commercial": commercial,
            "charger_count": charger_count,
            "search_radius_km": search_radius,
            "charger_to_vehicle": charger_to_vehicle,
        }

    @staticmethod
    def _accessibility_label(score):
        if score >= 75:
            return "Excellent"
        elif score >= 50:
            return "Good"
        elif score >= 25:
            return "Moderate"
        else:
            return "Limited"
