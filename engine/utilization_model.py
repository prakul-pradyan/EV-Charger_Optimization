"""
Utilization Forecast Model
===========================
Projects monthly charger utilization over N months based on:
  - Local EV density and population
  - Seasonal adjustment factors
  - EV adoption growth rate (18% YoY from MoRTH data)
  - Competition impact (demand shared with existing chargers)
  - Ramp-up curve (awareness takes time)
"""

import math


class UtilizationModel:

    # Monthly seasonal factors (1.0 = baseline)
    SEASONAL_FACTORS = {
        1: 0.90,   # Jan — mild winter
        2: 0.92,
        3: 0.96,
        4: 1.00,
        5: 1.05,   # Summer — more travel
        6: 0.95,   # Monsoon dip
        7: 0.88,
        8: 0.85,
        9: 0.92,
        10: 1.05,  # Festive
        11: 1.10,  # Peak festive
        12: 1.02,
    }

    def forecast(self, site, constants, months=6, start_month=1):
        """
        Generate month-by-month utilization forecast for a site.

        Returns list of dicts:
          [{ month: 1, utilization: 42.5, dailySessions: 11.2, revenue: ... }, ...]
        """
        composite = site.get("compositeScore", 50)
        population = site.get("population", 500000)
        chargers_nearby = site.get("chargersInRadius", 0)
        demand_score = site.get("scores", {}).get("demand", 50)
        tier = site.get("tier", 2)

        max_sessions = constants.get("maxSessionsPerDay", 32)
        avg_session_kwh = constants.get("avgSessionKwh", 25)
        tariff = constants.get("avgChargingTariffPerKwh", 20)
        growth_rate = constants.get("annualGrowthRate", 0.18)
        monthly_growth = (1 + growth_rate) ** (1 / 12) - 1

        # Base daily sessions from composite score
        # A perfect score (100) → ~24 sessions/day starting point
        base_sessions = (composite / 100) * 24

        # Competition dampener: much softer curve
        # Having more chargers means MORE demand (proven market), up to a point
        # Only very high density (>20) starts to hurt
        if chargers_nearby <= 5:
            competition_factor = 1.0 + chargers_nearby * 0.02  # Small boost from proven market
        elif chargers_nearby <= 15:
            competition_factor = 1.1 - (chargers_nearby - 5) * 0.015
        else:
            competition_factor = max(0.55, 0.95 - (chargers_nearby - 15) * 0.02)

        # Population multiplier (log scale, metros get bonus)
        pop_mult = min(1.5, 0.7 + math.log10(max(population, 100000)) * 0.12)

        # Tier bonus: metros attract more EV traffic
        tier_mult = {1: 1.15, 2: 1.0, 3: 0.85}.get(tier, 1.0)

        forecast = []
        for m in range(months):
            month_num = ((start_month - 1 + m) % 12) + 1

            # Ramp-up curve: awareness grows over time (sigmoid-like)
            ramp = 1.0 / (1.0 + math.exp(-1.0 * (m - 1.5)))  # Faster ramp, mid-point at month 2

            # Growth factor (compounded monthly)
            growth_mult = (1 + monthly_growth) ** m

            # Seasonal adjustment
            seasonal = self.SEASONAL_FACTORS.get(month_num, 1.0)

            # Daily sessions calculation
            daily_sessions = (
                base_sessions * ramp * competition_factor * pop_mult * tier_mult * growth_mult * seasonal
            )
            daily_sessions = min(daily_sessions, max_sessions)
            daily_sessions = max(daily_sessions, 1.0)

            utilization = (daily_sessions / max_sessions) * 100

            # Revenue
            daily_revenue = daily_sessions * avg_session_kwh * tariff
            monthly_revenue = daily_revenue * 30

            forecast.append(
                {
                    "month": m + 1,
                    "monthName": self._month_name(month_num),
                    "dailySessions": round(daily_sessions, 1),
                    "utilization": round(utilization, 1),
                    "monthlyRevenueLakh": round(monthly_revenue / 100000, 2),
                    "rampFactor": round(ramp, 3),
                    "seasonalFactor": seasonal,
                }
            )

        return forecast

    @staticmethod
    def _month_name(num):
        names = [
            "", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
            "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
        ]
        return names[num] if 1 <= num <= 12 else "?"
