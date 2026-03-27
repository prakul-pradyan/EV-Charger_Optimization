"""
EV Charger Optimisation — Flask Backend
Serves the frontend and provides API endpoints for:
  - Open Charge Map proxy (with caching)
  - Overpass/OSM POI proxy (with caching)
  - Scoring engine results
  - Utilization forecasts & break-even calculations
"""

import os
import json
import time
import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

from engine.scoring_engine import ScoringEngine
from engine.utilization_model import UtilizationModel
from engine.break_even_calc import BreakEvenCalculator
from api.open_charge_map import OpenChargeMapClient
from api.overpass import OverpassClient
from api.data_loader import DataLoader
from cache.cache_manager import CacheManager

# ── App Setup ────────────────────────────────────────────────────────
app = Flask(__name__, static_folder="static", static_url_path="")
CORS(app)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(BASE_DIR, ".cache")
DATA_DIR = os.path.join(BASE_DIR, "src", "data")

# ── Initialise components ────────────────────────────────────────────
cache = CacheManager(cache_dir=CACHE_DIR, memory_max_items=500, default_ttl=86400)
ocm_client = OpenChargeMapClient(cache=cache)
overpass_client = OverpassClient(cache=cache)
data_loader = DataLoader(data_dir=DATA_DIR)
scoring_engine = ScoringEngine()
utilization_model = UtilizationModel()
break_even_calc = BreakEvenCalculator()

# ── Analysis result cache ─────────────────────────────────────────────
# In-memory for instant re-serve
_analysis_cache = {"result": None, "weights_hash": None, "ts": 0}
_ANALYSIS_CACHE_TTL = 3600  # 1 hour in-memory


def _get_disk_analysis_path(w_hash):
    """Path for persisted analysis result on disk."""
    return os.path.join(CACHE_DIR, f"analysis_{w_hash}.json")


def _load_cached_analysis(w_hash):
    """Try to load analysis from disk cache."""
    path = _get_disk_analysis_path(w_hash)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Check TTL — 6 hour disk cache
            if time.time() - data.get("_ts", 0) < 21600:
                data.pop("_ts", None)
                return data
        except (json.JSONDecodeError, IOError):
            pass
    return None


def _save_analysis_to_disk(w_hash, result):
    """Persist analysis result to disk."""
    path = _get_disk_analysis_path(w_hash)
    try:
        save_data = {**result, "_ts": time.time()}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(save_data, f)
    except IOError as e:
        print(f"[CACHE] Failed to save analysis to disk: {e}")


# ── Static file serving ──────────────────────────────────────────────
@app.route("/")
def index():
    return send_from_directory("static", "index.html")


# ── API: Health check ────────────────────────────────────────────────
@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "cache_stats": cache.stats()})


# ── API: Get static datasets ────────────────────────────────────────
@app.route("/api/data/cities")
def get_cities():
    return jsonify(data_loader.get_cities())


@app.route("/api/data/ev-registrations")
def get_ev_registrations():
    return jsonify(data_loader.get_ev_registrations())


@app.route("/api/data/grid-capacity")
def get_grid_capacity():
    return jsonify(data_loader.get_grid_capacity())


# ── API: Open Charge Map (proxied & cached) ──────────────────────────
@app.route("/api/chargers/nearby")
def get_nearby_chargers():
    lat = request.args.get("lat", type=float)
    lng = request.args.get("lng", type=float)
    radius = request.args.get("radius", default=25, type=float)
    if lat is None or lng is None:
        return jsonify({"error": "lat and lng are required"}), 400
    data = ocm_client.get_nearby(lat, lng, radius_km=radius)
    return jsonify(data)


@app.route("/api/chargers/all-india")
def get_all_india_chargers():
    """Fetch all chargers for India (cached heavily)."""
    data = ocm_client.get_all_india()
    return jsonify(data)


# ── API: OSM POIs (proxied & cached) ─────────────────────────────────
@app.route("/api/pois/nearby")
def get_nearby_pois():
    lat = request.args.get("lat", type=float)
    lng = request.args.get("lng", type=float)
    radius = request.args.get("radius", default=5000, type=int)
    if lat is None or lng is None:
        return jsonify({"error": "lat and lng are required"}), 400
    data = overpass_client.get_pois(lat, lng, radius_m=radius)
    return jsonify(data)


def _fetch_city_pois_batch(cities, max_workers=4):
    """
    Fetch POIs for all cities using thread pool.
    Each call uses per-key cache, so only uncached cities trigger API calls.
    Reduced workers to 4 to respect Overpass rate limits.
    """
    city_pois = {}
    uncached = []

    # First pass: check what's already cached
    for city in cities:
        key = f"{city['lat']}_{city['lng']}"
        cached_poi = overpass_client.get_cached_pois(city["lat"], city["lng"])
        if cached_poi is not None:
            city_pois[key] = cached_poi
        else:
            uncached.append(city)

    if not uncached:
        return city_pois

    print(f"[ANALYSIS] {len(city_pois)} cities cached, {len(uncached)} need API fetch")

    # Second pass: fetch uncached in parallel
    def fetch_one(city):
        key = f"{city['lat']}_{city['lng']}"
        pois = overpass_client.get_pois(city["lat"], city["lng"], radius_m=25000)
        return key, pois

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(fetch_one, city): city for city in uncached}
        for future in as_completed(futures):
            try:
                key, pois = future.result()
                city_pois[key] = pois
            except Exception as e:
                city = futures[future]
                city_pois[f"{city['lat']}_{city['lng']}"] = {
                    "data": overpass_client._default_pois(),
                    "source": "DEFAULT",
                }

    return city_pois


def _weights_hash(weights):
    """Create a hash of weight overrides for cache key."""
    raw = json.dumps(weights, sort_keys=True)
    return hashlib.md5(raw.encode()).hexdigest()


# ── API: Run Scoring Engine ──────────────────────────────────────────
@app.route("/api/analysis/run", methods=["POST"])
def run_analysis():
    """
    Run the full site-selection analysis.
    Accepts optional JSON body with weight overrides.
    Returns ranked top-50 locations with all KPIs.
    """
    global _analysis_cache
    t_start = time.time()

    weights = request.get_json(silent=True) or {}
    w_hash = _weights_hash(weights)

    # ── Layer 1: In-memory cache (instant) ──
    if (
        _analysis_cache["result"] is not None
        and _analysis_cache["weights_hash"] == w_hash
        and (time.time() - _analysis_cache["ts"]) < _ANALYSIS_CACHE_TTL
    ):
        result = _analysis_cache["result"]
        result["meta"] = {"cached": True, "cacheSource": "memory", "computeTimeMs": 0}
        return jsonify(result)

    # ── Layer 2: Disk cache (fast, survives restarts) ──
    disk_result = _load_cached_analysis(w_hash)
    if disk_result is not None:
        _analysis_cache = {"result": disk_result, "weights_hash": w_hash, "ts": time.time()}
        disk_result["meta"] = {"cached": True, "cacheSource": "disk", "computeTimeMs": 0}
        return jsonify(disk_result)

    # ── Layer 3: Full computation ──
    print("[ANALYSIS] Cache miss — running full analysis...")
    cities = data_loader.get_cities()
    ev_data = data_loader.get_ev_registrations()
    grid_data = data_loader.get_grid_capacity()

    # Fetch charger data (cached at OCM level — single bulk API call)
    all_chargers = ocm_client.get_all_india()
    t_chargers = time.time()
    print(f"[ANALYSIS] Charger data: {all_chargers.get('count', 0)} chargers ({round(t_chargers - t_start, 1)}s)")

    # Fetch POI data — check cache first, then fetch missing in parallel
    city_pois = _fetch_city_pois_batch(cities, max_workers=4)
    t_pois = time.time()
    print(f"[ANALYSIS] POI data ready ({round(t_pois - t_chargers, 1)}s)")

    # Score all cities
    scored = scoring_engine.score_all(
        cities=cities,
        ev_data=ev_data,
        grid_data=grid_data,
        chargers=all_chargers,
        pois=city_pois,
        weight_overrides=weights,
    )
    t_scored = time.time()
    print(f"[ANALYSIS] Scoring complete ({round(t_scored - t_pois, 1)}s)")

    # Only compute utilization & break-even for top 50 (not all cities)
    top50 = scored[:50]
    constants = grid_data.get("constants", {})

    # Pre-build state_grid lookup (avoid repeated linear scan)
    regions = grid_data.get("regions", [])
    state_grid_lookup = {r["state"]: r for r in regions}

    for site in top50:
        state_grid = state_grid_lookup.get(site["state"], {})
        site["utilizationForecast"] = utilization_model.forecast(
            site, constants, months=6
        )
        site["breakEven"] = break_even_calc.calculate(
            site, constants, state_grid
        )

    # Summary KPIs
    avg_util = (
        sum(s["utilizationForecast"][-1]["utilization"] for s in top50) / len(top50)
        if top50
        else 0
    )
    # For break-even avg, exclude non-viable sites (999)
    viable_be = [s["breakEven"]["months"] for s in top50 if s["breakEven"]["months"] < 999]
    avg_breakeven = sum(viable_be) / len(viable_be) if viable_be else 0
    total_investment = sum(s["breakEven"]["investmentLakh"] for s in top50)

    elapsed_ms = round((time.time() - t_start) * 1000)
    print(f"[ANALYSIS] Total time: {elapsed_ms}ms")

    summary = {
        "totalSites": len(top50),
        "avgUtilization": round(avg_util, 1),
        "avgBreakEvenMonths": round(avg_breakeven, 1),
        "totalInvestmentCrore": round(total_investment / 100, 2),
    }

    result = {
        "summary": summary,
        "sites": top50,
        "meta": {"cached": False, "cacheSource": "compute", "computeTimeMs": elapsed_ms},
    }

    # Cache to memory AND disk
    _analysis_cache = {"result": result, "weights_hash": w_hash, "ts": time.time()}
    _save_analysis_to_disk(w_hash, result)

    return jsonify(result)


# ── API: Single site deep-dive ───────────────────────────────────────
@app.route("/api/analysis/site/<int:rank>")
def site_detail(rank):
    """Get detailed analysis for a specific ranked site."""
    return jsonify({"message": "Use /api/analysis/run and filter by rank", "rank": rank})


# ── API: Cache management ────────────────────────────────────────────
@app.route("/api/cache/stats")
def cache_stats():
    return jsonify(cache.stats())


@app.route("/api/cache/clear", methods=["POST"])
def cache_clear():
    global _analysis_cache
    tier = request.args.get("tier", "all")
    cache.clear(tier=tier)
    _analysis_cache = {"result": None, "weights_hash": None, "ts": 0}
    # Also clear disk analysis cache
    for f in os.listdir(CACHE_DIR):
        if f.startswith("analysis_") and f.endswith(".json"):
            os.remove(os.path.join(CACHE_DIR, f))
    return jsonify({"status": "cleared", "tier": tier})


# ── Run ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    os.makedirs(CACHE_DIR, exist_ok=True)
    print("\n⚡ EV Charger Optimisation Server")
    print(f"   Cache dir: {CACHE_DIR}")
    print(f"   Data dir:  {DATA_DIR}")
    print(f"   Open http://localhost:5000\n")
    app.run(debug=True, host="0.0.0.0", port=5000)
