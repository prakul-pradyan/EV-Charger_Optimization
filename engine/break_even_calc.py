"""
Break-Even Calculator
======================
Financial model for EV fast-charger installation:
  - Installation cost: ₹25–35 lakh (50kW DC, all-inclusive)
  - Revenue: sessions × energy × tariff
  - Operating costs: electricity, maintenance, land lease
  - Subsidy offset: PM E-DRIVE (up to 80% infra + 70% equipment)
  - Output: months to break-even at projected utilization
"""


class BreakEvenCalculator:

    def calculate(self, site, constants, state_grid):
        """
        Calculate break-even timeline for a candidate site.

        Returns dict with:
          - investmentLakh: total upfront ₹ in lakhs
          - subsidyLakh: subsidy amount
          - netInvestmentLakh: after subsidy
          - monthlyRevenue / monthlyCost
          - months: months to break-even
          - profitable: bool
        """
        # ── Costs ──
        install_cost_lakh = constants.get("installationCostLakh", 30)
        monthly_maintenance = constants.get("maintenanceCostMonthly", 12000)
        monthly_lease = constants.get("landLeaseMonthly", 20000)

        # Tier-based land cost adjustment (more realistic)
        tier = site.get("tier", 2)
        lease_multiplier = {1: 1.3, 2: 1.0, 3: 0.6}.get(tier, 1.0)
        adjusted_lease = monthly_lease * lease_multiplier

        # Subsidy
        subsidy_infra_pct = constants.get("subsidyPercentInfra", 80) / 100
        subsidy_equip_pct = constants.get("subsidyPercentEquipment", 70) / 100
        # Split: ~40% is infra, ~60% is equipment
        infra_cost = install_cost_lakh * 0.4
        equip_cost = install_cost_lakh * 0.6
        subsidy_lakh = infra_cost * subsidy_infra_pct + equip_cost * subsidy_equip_pct
        net_investment = install_cost_lakh - subsidy_lakh

        # ── Revenue ──
        forecast = site.get("utilizationForecast", [])
        avg_session_kwh = constants.get("avgSessionKwh", 25)
        charging_tariff = constants.get("avgChargingTariffPerKwh", 20)

        # Electricity procurement cost
        elec_tariff = state_grid.get("avgTariffPerKwh", 6)

        # ── Monthly cashflow simulation ──
        cumulative = -(net_investment * 100000)  # Convert lakh to rupees
        breakeven_month = None
        monthly_details = []

        for month_data in forecast:
            daily_sessions = month_data.get("dailySessions", 5)
            monthly_kwh = daily_sessions * avg_session_kwh * 30

            revenue = monthly_kwh * charging_tariff
            elec_cost = monthly_kwh * elec_tariff
            total_cost = elec_cost + monthly_maintenance + adjusted_lease
            net_profit = revenue - total_cost

            cumulative += net_profit

            monthly_details.append(
                {
                    "month": month_data["month"],
                    "revenue": round(revenue),
                    "cost": round(total_cost),
                    "netProfit": round(net_profit),
                    "cumulative": round(cumulative),
                }
            )

            if cumulative >= 0 and breakeven_month is None:
                breakeven_month = month_data["month"]

        # If not broken even in forecast period, extrapolate
        if breakeven_month is None and monthly_details:
            last = monthly_details[-1]
            if last["netProfit"] > 0:
                remaining = -last["cumulative"]
                extra_months = remaining / last["netProfit"]
                breakeven_month = len(monthly_details) + int(extra_months) + 1
            else:
                breakeven_month = 999  # Not viable

        # Average monthly values (for display)
        if monthly_details:
            avg_revenue = sum(m["revenue"] for m in monthly_details) / len(monthly_details)
            avg_cost = sum(m["cost"] for m in monthly_details) / len(monthly_details)
        else:
            avg_revenue = 0
            avg_cost = monthly_maintenance + adjusted_lease

        return {
            "investmentLakh": round(install_cost_lakh, 2),
            "subsidyLakh": round(subsidy_lakh, 2),
            "netInvestmentLakh": round(net_investment, 2),
            "monthlyRevenue": round(avg_revenue),
            "monthlyCost": round(avg_cost),
            "monthlyProfit": round(avg_revenue - avg_cost),
            "months": breakeven_month or 999,
            "profitable": (avg_revenue - avg_cost) > 0,
            "roiPercent": round(
                ((avg_revenue - avg_cost) * 12 / max(net_investment * 100000, 1)) * 100, 1
            ),
            "monthlyDetails": monthly_details,
        }
