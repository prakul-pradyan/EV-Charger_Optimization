import urllib.request
import json

cities_payload = [
    {
        "city": "Mega-Metro-X",
        "state": "State-A",
        "tier": 1,
        "population": 15000000,
        "compositeScore": 85.5,
        "scores": {"demand": 90, "competition": 80, "accessibility": 95, "grid": 85, "commercial": 90},
        "chargersInRadius": 1000,
        "chargerToVehicleRatio": 0.02
    },
    {
        "city": "Small-Town-Y",
        "state": "State-B",
        "tier": 3,
        "population": 500000,
        "compositeScore": 35.0,
        "scores": {"demand": 40, "competition": 80, "accessibility": 30, "grid": 45, "commercial": 20},
        "chargersInRadius": 5,
        "chargerToVehicleRatio": 0.001
    },
    # Generating a few more dummies so DBSCAN and KMeans have > 10 data points as required by our check
]

# Expanding the payload up to 12 cities so our `len(cities) < 10` check passes
for i in range(10):
    cities_payload.append({
        "city": f"Dummy-City-{i}",
        "state": "State-C",
        "tier": 2,
        "population": 2000000 + i*100000,
        "compositeScore": 55.0 + i,
        "scores": {"demand": 50+i, "competition": 50, "accessibility": 60, "grid": 60, "commercial": 50},
        "chargersInRadius": 50 + i*5,
        "chargerToVehicleRatio": 0.005
    })

data = json.dumps(cities_payload).encode('utf-8')
req = urllib.request.Request(
    'http://localhost:5000/api/ml-insights',
    data=data,
    headers={'Content-Type': 'application/json'},
    method='POST'
)

try:
    with urllib.request.urlopen(req) as response:
        result = json.loads(response.read().decode('utf-8'))
        
        print("✅ ML Insights Successfully Derived!")
        print("-" * 50)
        
        # Print summary
        summary = result.get('summary', {})
        print(f"K-Means Clusters: {summary.get('kmeans_clusters_found')}")
        print(f"K-Means Silhouette Score: {summary.get('kmeans_silhouette')}")
        print(f"DBSCAN Outliers/Clusters: {summary.get('dbscan_clusters_found')}")
        
        print("\n📍 City Categorisations:")
        # Print top 3 categorized cities
        for city in result.get('data', [])[:3]:
            print(f" - {city['city']} | Tag: {city['kmeans_label']} | DBSCAN: {city['dbscan_label']}")
            
except Exception as e:
    print(f"❌ Error: {e}")
