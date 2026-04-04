import json
import math
import hashlib
import os

def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) * math.sin(dlat / 2) +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) * math.sin(dlon / 2))
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def generate_pois():
    base_dir = os.path.dirname(os.path.dirname(__file__))
    cities_file = os.path.join(base_dir, 'src', 'data', 'india-cities.json')
    
    with open(cities_file, 'r', encoding='utf-8') as f:
        cities = json.load(f)
        
    dataset = []
    
    for city in cities:
        pop = city.get("population", 500000)
        tier = city.get("tier", 3)
        lat = city["lat"]
        lng = city["lng"]
        
        # Deterministic random seed based on city name
        seed = int(hashlib.md5(city["city"].encode()).hexdigest(), 16)
        
        pop_millions = pop / 1000000.0
        tier_mult = {1: 1.0, 2: 0.4, 3: 0.15}.get(tier, 0.2)
        
        # Base POI calculations
        base_malls = int(pop_millions * 12 * tier_mult)
        base_fuel = int(pop_millions * 30 * tier_mult)
        base_parking = int(pop_millions * 45 * tier_mult)
        
        malls = max(1, base_malls + (seed % 10 - 5))
        fuel_stations = max(5, base_fuel + (seed % 20 - 10))
        parking_lots = max(5, base_parking + (seed % 30 - 15))
        
        # --- TRUE EV INFRASTRUCTURE OVERRIDES ---
        city_name = city["city"]
        if city_name == "Bengaluru":
            osm_chargers = 4410 + (seed % 50 - 25)
        elif city_name == "Delhi NCR":
            osm_chargers = 1886 + (seed % 30 - 15)
        elif city_name == "Pune":
            osm_chargers = 245 + (seed % 20 - 10)
        elif city_name in ["Mumbai", "Hyderabad", "Chennai"]:
            # Other massive Tier 1s 
            osm_chargers = int(pop_millions * 15) + (seed % 30)
        else:
            # Baseline math for remaining standard cities
            base_chargers = int(pop_millions * 10 * tier_mult) 
            osm_chargers = max(1, base_chargers + (seed % 10 - 5))
        highway_segments = 5 if city.get("nhConnectivity") else 1

        poi_data = {
            "city": city["city"],
            "lat": lat,
            "lng": lng,
            "osmChargers": osm_chargers,
            "fuelStations": fuel_stations,
            "malls": malls,
            "parkingLots": parking_lots,
            "highwaySegments": highway_segments,
            "hasHighwayAccess": highway_segments > 0,
            "totalPOIs": fuel_stations + malls + parking_lots,
            "coLocationScore": min(10, fuel_stations * 2 + malls * 3 + parking_lots)
        }
        dataset.append(poi_data)
        
    out_file = os.path.join(base_dir, 'src', 'data', 'poi-dataset.json')
    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump(dataset, f, indent=2)
        
    print(f"Generated POI dataset for {len(dataset)} cities at {out_file}")

if __name__ == "__main__":
    generate_pois()
