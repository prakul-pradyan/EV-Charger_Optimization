# EV Charger Optimisation ⚡

An advanced, data-driven Site Selection and Utilization Forecast dashboard designed to identify the optimal locations for new EV fast-charging infrastructure across India.

## Overview
As the EV infrastructure market rapidly expands, deciding where to deploy capital-intensive DC fast-chargers is critical. This application processes real-world demographic, traffic, and existing infrastructure data to rank the top 50 cities and micro-markets for EV charger deployment.

It provides actionable intelligence on:
- **Projected Utilization Rates** (6-month forecast)
- **Break-Even Timelines** (financial ROI modeling)
- **Competition vs. Demand Dynamics** (Charger-to-Vehicle Ratio)

## Features

- **Spatial Scoring Engine**: Evaluates locations based on a 5-pillar composite scoring system:
  1. **Demand Score (30%)**: Current EV penetration, population density, and State-wise EV growth rates (MoRTH data).
  2. **Competition Score (25%)**: Real-time analysis of existing chargers within a dynamic search radius (25km for Tier 1, 15km for Tier 2).
  3. **Accessibility Score (20%)**: Proximity to highways, motorways, and key Points of Interest (POIs).
  4. **Grid Score (15%)**: Regional power reliability and commercial electricity tariffs.
  5. **Commercial Viability (10%)**: Co-location opportunities like shopping malls and fuel stations.

- **Real-Time API Integrations**:
  - **Open Charge Map (OCM) API**: Fetches existing public charging stations across India.
  - **Overpass API (OpenStreetMap)**: Dynamically fetches local POIs (malls, parking lots) and highway connectivity for candidate sites.

- **Financial Modeling Pipeline**: Simulates month-over-month cash flow considering hardware costs, land leases, grid tariffs, government subsidies (PM E-DRIVE), and seasonal utilization fluctuations to project an accurate break-even month.

- **High-Performance Caching**: Features a multi-tiered caching system (Memory + Disk JSON) to bypass rate-limits from free-tier APIs and instantly serve subsequent dashboard visits.

## Tech Stack

- **Backend**: Python, Flask, Flask-CORS
- **Frontend**: HTML5, Vanilla CSS, Vanilla JavaScript
- **Mapping**: Leaflet.js, CartoDB Map Tiles, Leaflet.markercluster
- **Data Visualization**: Chart.js

## Project Structure

```text
ev-charger-optimisation/
├── app.py                     # Main Flask Application
├── api/                       # External API integrations
│   ├── open_charge_map.py     # OCM client & fallback logic
│   ├── overpass.py            # OpenStreetMap POI client
│   └── data_loader.py         # Static dataset manager
├── engine/                    # Core calculation engines
│   ├── scoring_engine.py      # Spatial & composite scoring logic
│   ├── utilization_model.py   # Forecasts daily sessions & usage
│   └── break_even_calc.py     # Financial simulation model
├── src/data/                  # Curated Datasets
│   ├── chargers-fallback.json # Failsafe mapping of chargers
│   ├── ev-registrations.json  # MoRTH EV data per state
│   ├── grid-capacity.json     # Power reliability & tariffs
│   └── india-cities.json      # 100 candidate micro-markets
├── cache/                     # Tiered caching module
└── static/                    # Frontend UI layer
    ├── index.html             
    ├── app.js                 
    └── style.css              
```

## Setup and Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/prakul-pradyan/EV-Charger_Optimization.git
   cd EV-Charger_Optimization
   ```

2. **Install dependencies**:
   Ensure you have Python 3.8+ installed.
   ```bash
   pip install -r requirements.txt
   ```

3. **Environment Setup**:
   The `Open Charge Map` API key is already configured internally. No `.env` is strictly required for the core to run, however standard rate-limits apply to the free Overpass API.

4. **Run the Application**:
   ```bash
   python app.py
   ```
   *The server will start on `http://localhost:5000`.*

## Usage

1. Open `http://localhost:5000` in your browser.
2. Click **Run Analysis** to execute the pipeline.
3. *Note: The very first run may take 60-90 seconds as it actively fetches live POI data for 100 cities from OpenStreetMap and populates the `.cache/` directory. Subsequent runs will load near-instantly.*
4. Use the sidebar filters to isolate specific States, City Tiers, or minimum Composite Scores.
5. Click on any row in the **Ranked Sites** table or any marker on the map to view a deep-dive modal detailing the exact sub-scores and projected cash flow for that micro-market.

## License
Proprietary / Educational Use. Data provided by OCM and OSM fall under their respective ODbL/creative commons licenses.
