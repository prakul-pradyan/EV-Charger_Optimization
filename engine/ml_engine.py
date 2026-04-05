"""
Machine Learning Engine
========================
Provides K-Means and DBSCAN clustering insights for EV charger site selection.
Groups cities into distinct viability tiers based on multiple feature dimensions.
"""

import numpy as np
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans, DBSCAN
from sklearn.metrics import silhouette_score

class MLEngine:
    def __init__(self):
        self.scaler = StandardScaler()

    def _extract_features(self, cities):
        """
        Safely extracts the requested numerical features from the city dictionary,
        handling slight naming variations between the prompt and the actual pipeline.
        """
        X = []
        for city in cities:
            composite = city.get("compositeScore", city.get("composite_score", 0))
            
            # Scores sub-dictionary or top level
            scores = city.get("scores", city)
            demand = scores.get("demand", scores.get("demand_score", 0))
            competition = scores.get("competition", scores.get("competition_score", 0))
            accessibility = scores.get("accessibility", scores.get("accessibility_score", 0))
            grid = scores.get("grid", scores.get("grid_score", 0))
            commercial = scores.get("commercial", scores.get("commercial_score", 0))
            
            pop = city.get("population", 0) / 1000000.0  # Normalized to millions
            chargers = city.get("chargersInRadius", city.get("existing_chargers", 0))
            
            # Fallback for ev_registrations (approximate from city_ev_share logic if missing)
            raw = city.get("raw", {})
            charger_to_veh = city.get("chargerToVehicleRatio", 0.0001)
            estimated_evs = int(chargers / max(charger_to_veh, 0.0001))
            ev_regs = city.get("ev_registrations", estimated_evs)
            
            tier = city.get("tier", city.get("city_tier", 2))
            
            X.append([
                composite, demand, competition, accessibility, 
                grid, commercial, pop, chargers, ev_regs, tier
            ])
            
        return np.array(X)
        
    def _get_cluster_labels(self, labels, composite_scores):
        """
        Maps cluster IDs to literal string labels by ranking their average composite score.
        Highest average -> Priority Expansion, Lowest -> Low Viability
        """
        # Calculate mean composite score for each cluster (ignoring noise -1)
        unique_labels = set(labels)
        cluster_means = {}
        for c in unique_labels:
            if c == -1:
                continue
            idx = np.where(labels == c)[0]
            cluster_means[c] = np.mean(composite_scores[idx])
            
        # Sort cluster IDs by descending mean composite score
        sorted_clusters = sorted(cluster_means.keys(), key=lambda x: cluster_means[x], reverse=True)
        
        # Determine labels mapping based on the number of clusters found
        mapping = {}
        target_labels = ["Priority Expansion", "Emerging Market", "Saturated Zone", "Low Viability"]
        
        for i, c in enumerate(sorted_clusters):
            # If DBSCAN finds more than 4, just clamp it to Low Viability for trailing ones
            mapping[c] = target_labels[i] if i < len(target_labels) else "Low Viability"
            
        # Add mapping for noise if present
        mapping[-1] = "Outlier / Anomaly"
        
        return mapping

    def generate_insights(self, cities):
        """
        Runs both algorithms, computes metrics, and enriches the input city data.
        """
        if not cities or len(cities) < 10:
            # Need enough data to run robust clustering
            return cities, {"error": "Insufficient data points"}
            
        # 1. Prepare and scale features
        X = self._extract_features(cities)
        X_scaled = self.scaler.fit_transform(X)
        composite_scores = X[:, 0]  # The first column is compositeScore

        # 2. Elbow Method (k=2 to 10)
        elbow_curve = []
        for k in range(2, min(11, len(cities))):
            km = KMeans(n_clusters=k, random_state=42, n_init="auto")
            km.fit(X_scaled)
            elbow_curve.append(float(km.inertia_))
            
        # 3. K-Means implementation
        kmeans = KMeans(n_clusters=4, random_state=42, n_init="auto")
        k_labels = kmeans.fit_predict(X_scaled)
        try:
            k_silhouette = float(silhouette_score(X_scaled, k_labels))
        except ValueError:
            k_silhouette = 0.0
            
        k_mapping = self._get_cluster_labels(k_labels, composite_scores)

        # 4. DBSCAN implementation
        dbscan = DBSCAN(eps=2.0, min_samples=3)
        db_labels = dbscan.fit_predict(X_scaled)
        
        # Only compute silhouette if more than 1 cluster (excluding noise)
        valid_clusters = set(db_labels) - {-1}
        try:
            if len(valid_clusters) >= 2:
                db_silhouette = float(silhouette_score(X_scaled, db_labels))
            else:
                db_silhouette = 0.0
        except ValueError:
            db_silhouette = 0.0
            
        db_mapping = self._get_cluster_labels(db_labels, composite_scores)

        # 5. Enrich city dictionaries
        enriched_cities = []
        for i, city_dict in enumerate(cities):
            # Create a shallow copy to prevent modifying the base cache directly
            enriched = city_dict.copy()
            enriched["kmeans_cluster"] = int(k_labels[i])
            enriched["kmeans_label"] = k_mapping[int(k_labels[i])]
            enriched["dbscan_cluster"] = int(db_labels[i])
            enriched["dbscan_label"] = db_mapping[int(db_labels[i])]
            enriched_cities.append(enriched)
            
        # 6. Build model summary
        model_summary = {
            "kmeans_clusters_found": 4,
            "kmeans_silhouette": k_silhouette,
            "dbscan_clusters_found": len(valid_clusters),
            "dbscan_silhouette": db_silhouette,
            "elbow_curve": elbow_curve
        }
        
        return enriched_cities, model_summary
