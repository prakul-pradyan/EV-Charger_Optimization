/* ═══════════════════════════════════════════════════════════════
   EV Charger Optimisation — Frontend Application
   ═══════════════════════════════════════════════════════════════ */

const API = '';  // Same origin

// ── State ────────────────────────────────────────────────────
let analysisData = null;
let filteredSites = [];
let map = null;
let markerGroup = null;
let existingMarkersGroup = null;
let charts = {};
let sortCol = 'rank';
let sortAsc = true;

// ── Init ─────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    initMap();
    initEventListeners();
    fetchCacheStatus();
});

// ── MAP ──────────────────────────────────────────────────────
function initMap() {
    map = L.map('map', {
        center: [22.5, 78.5],
        zoom: 5,
        zoomControl: true,
        attributionControl: false,
    });

    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
        maxZoom: 18,
    }).addTo(map);

    markerGroup = L.markerClusterGroup({
        maxClusterRadius: 40,
        spiderfyOnMaxZoom: true,
        showCoverageOnHover: false,
        iconCreateFunction: (cluster) => {
            const count = cluster.getChildCount();
            let cls = 'score-high';
            if (count > 15) cls = 'score-mid';
            return L.divIcon({
                html: `<div class="cluster-icon ${cls}">${count}</div>`,
                className: 'custom-cluster',
                iconSize: [36, 36],
            });
        },
    });
    map.addLayer(markerGroup);

    existingMarkersGroup = L.layerGroup().addTo(map);
}

function updateMap(sites) {
    markerGroup.clearLayers();

    sites.forEach((site) => {
        const color = site.compositeScore >= 75 ? '#00ff88'
            : site.compositeScore >= 50 ? '#ffb800' : '#ff3366';

        const icon = L.divIcon({
            className: 'custom-marker',
            html: `<div class="pulse-marker" style="background:${color};color:${color};box-shadow:0 0 10px ${color}55;">
                    <span style="position:absolute;top:-18px;left:50%;transform:translateX(-50%);font-size:10px;font-weight:700;color:${color};white-space:nowrap;">#${site.rank}</span>
                   </div>`,
            iconSize: [18, 18],
            iconAnchor: [9, 9],
        });

        const marker = L.marker([site.lat, site.lng], { icon });
        marker.bindPopup(createPopup(site), {
            maxWidth: 300,
            className: 'dark-popup',
        });
        marker.on('click', () => highlightTableRow(site.rank));
        markerGroup.addLayer(marker);
    });
}

function createPopup(site) {
    const be = site.breakEven || {};
    return `
        <div style="font-family:Inter,sans-serif;color:#e8edf5;min-width:220px;">
            <div style="font-size:14px;font-weight:700;margin-bottom:2px;">#${site.rank} ${site.city}</div>
            <div style="font-size:11px;color:#8892a8;margin-bottom:10px;">${site.state} · ${site.lat.toFixed(4)}, ${site.lng.toFixed(4)}</div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;font-size:11px;">
                <div><span style="color:#8892a8;">Score</span><br><strong style="color:#00d4ff;">${site.compositeScore.toFixed(1)}</strong></div>
                <div><span style="color:#8892a8;">Utilization</span><br><strong style="color:#00ff88;">${getLastUtil(site)}%</strong></div>
                <div><span style="color:#8892a8;">C:V Ratio</span><br><strong>${site.chargerToVehicleRatio.toFixed(4)}</strong></div>
                <div><span style="color:#8892a8;">Break-even</span><br><strong style="color:#ffb800;">${be.months || '—'} mo</strong></div>
            </div>
            <div style="margin-top:8px;font-size:10px;color:#4a5568;cursor:pointer;" onclick="showSiteDetail(${site.rank})">Click for full details →</div>
        </div>`;
}

// ── KPI CARDS ────────────────────────────────────────────────
function updateKPIs(summary) {
    animateValue('kpi-sites-value', 0, summary.totalSites, 800, '', '');
    animateValue('kpi-util-value', 0, summary.avgUtilization, 1000, '', '%');
    animateValue('kpi-be-value', 0, summary.avgBreakEvenMonths, 900, '', ' mo');
    animateValue('kpi-inv-value', 0, summary.totalInvestmentCrore, 1100, '₹', ' Cr');
}

function animateValue(id, start, end, duration, prefix = '', suffix = '') {
    const el = document.getElementById(id);
    const startTime = performance.now();
    const isFloat = !Number.isInteger(end);

    function update(currentTime) {
        const elapsed = currentTime - startTime;
        const progress = Math.min(elapsed / duration, 1);
        const eased = 1 - Math.pow(1 - progress, 3);
        const current = start + (end - start) * eased;
        el.textContent = prefix + (isFloat ? current.toFixed(1) : Math.round(current)) + suffix;
        if (progress < 1) requestAnimationFrame(update);
    }
    requestAnimationFrame(update);
}

// ── TABLE ────────────────────────────────────────────────────
function updateTable(sites) {
    const tbody = document.getElementById('sites-tbody');

    if (!sites.length) {
        tbody.innerHTML = '<tr><td colspan="7" class="empty-state">No sites match your filters</td></tr>';
        return;
    }

    tbody.innerHTML = sites.map(site => {
        const be = site.breakEven || {};
        const scoreClass = site.compositeScore >= 75 ? 'score-high'
            : site.compositeScore >= 50 ? 'score-mid' : 'score-low';
            
        const mlLabel = site.kmeans_label || 'Uncategorised';
        let mlClass = 'badge-low';
        if (mlLabel === 'Priority Expansion') mlClass = 'badge-priority';
        else if (mlLabel === 'Emerging Market') mlClass = 'badge-emerging';
        else if (mlLabel === 'Saturated Zone') mlClass = 'badge-saturated';
            
        return `
            <tr data-rank="${site.rank}" onclick="showSiteDetail(${site.rank})">
                <td style="font-weight:700;color:var(--accent-primary);">${site.rank}</td>
                <td>
                    <div style="font-weight:600;">${site.city}</div>
                    <div style="font-size:0.66rem;color:var(--text-muted);">${site.state}</div>
                </td>
                <td><span class="score-badge ${scoreClass}">${site.compositeScore.toFixed(1)}</span></td>
                <td>${site.chargerToVehicleRatio.toFixed(4)}</td>
                <td><span class="ml-badge ${mlClass}">${mlLabel}</span></td>
                <td>${site.accessibilityLabel}</td>
                <td>${be.months !== undefined && be.months < 999 ? be.months + ' mo' : 'N/A'}</td>
            </tr>`;
    }).join('');
}

function highlightTableRow(rank) {
    document.querySelectorAll('#sites-table tbody tr').forEach(tr => tr.classList.remove('highlighted'));
    const row = document.querySelector(`tr[data-rank="${rank}"]`);
    if (row) {
        row.classList.add('highlighted');
        row.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
}

// ── CHARTS ───────────────────────────────────────────────────
function updateCharts(sites) {
    destroyCharts();
    if (!sites.length) return;

    const top20 = sites.slice(0, 20);
    const top5 = sites.slice(0, 5);

    // 1. Score Distribution
    charts.scores = new Chart(document.getElementById('chart-scores'), {
        type: 'bar',
        data: {
            labels: top20.map(s => s.city),
            datasets: [{
                label: 'Composite Score',
                data: top20.map(s => s.compositeScore),
                backgroundColor: top20.map(s =>
                    s.compositeScore >= 75 ? '#00ff8840' : s.compositeScore >= 50 ? '#ffb80040' : '#ff336640'),
                borderColor: top20.map(s =>
                    s.compositeScore >= 75 ? '#00ff88' : s.compositeScore >= 50 ? '#ffb800' : '#ff3366'),
                borderWidth: 1.5,
                borderRadius: 4,
            }]
        },
        options: chartOptions('Score'),
    });

    // 2. Utilization Forecast
    const colors = ['#00d4ff', '#00ff88', '#a855f7', '#ffb800', '#ff3366'];
    charts.utilization = new Chart(document.getElementById('chart-utilization'), {
        type: 'line',
        data: {
            labels: ['Month 1', 'Month 2', 'Month 3', 'Month 4', 'Month 5', 'Month 6'],
            datasets: top5.map((s, i) => ({
                label: s.city,
                data: (s.utilizationForecast || []).map(f => f.utilization),
                borderColor: colors[i],
                backgroundColor: colors[i] + '15',
                fill: true,
                tension: 0.4,
                pointRadius: 4,
                pointHoverRadius: 6,
                borderWidth: 2,
            })),
        },
        options: chartOptions('Utilization %'),
    });

    // 3. State-wise Opportunity
    const stateScores = {};
    sites.forEach(s => {
        stateScores[s.state] = (stateScores[s.state] || 0) + s.compositeScore;
    });
    const sortedStates = Object.entries(stateScores).sort((a, b) => b[1] - a[1]).slice(0, 12);

    charts.states = new Chart(document.getElementById('chart-states'), {
        type: 'bar',
        data: {
            labels: sortedStates.map(s => s[0]),
            datasets: [{
                label: 'Cumulative Score',
                data: sortedStates.map(s => Math.round(s[1])),
                backgroundColor: '#00d4ff30',
                borderColor: '#00d4ff',
                borderWidth: 1.5,
                borderRadius: 4,
            }],
        },
        options: { ...chartOptions('Total Score'), indexAxis: 'y' },
    });

    // 4. Investment vs Break-Even
    const viable = sites.filter(s => s.breakEven && s.breakEven.months < 999);
    charts.breakeven = new Chart(document.getElementById('chart-breakeven'), {
        type: 'scatter',
        data: {
            datasets: [{
                label: 'Sites',
                data: viable.map(s => ({
                    x: s.breakEven.netInvestmentLakh,
                    y: s.breakEven.months,
                    city: s.city,
                })),
                backgroundColor: viable.map(s =>
                    s.breakEven.months <= 18 ? '#00ff8880' : s.breakEven.months <= 36 ? '#ffb80080' : '#ff336680'),
                pointRadius: 6,
                pointHoverRadius: 9,
            }],
        },
        options: {
            ...chartOptions('Break-Even Months'),
            scales: {
                x: {
                    title: { display: true, text: 'Net Investment (₹ Lakh)', color: '#8892a8' },
                    grid: { color: 'rgba(255,255,255,0.04)' },
                    ticks: { color: '#8892a8' },
                },
                y: {
                    title: { display: true, text: 'Break-Even (Months)', color: '#8892a8' },
                    grid: { color: 'rgba(255,255,255,0.04)' },
                    ticks: { color: '#8892a8' },
                },
            },
            plugins: {
                tooltip: {
                    callbacks: {
                        label: (ctx) => `${ctx.raw.city}: ₹${ctx.raw.x}L, ${ctx.raw.y} months`,
                    },
                },
                legend: { display: false },
            },
        },
    });
}

function chartOptions(yLabel) {
    return {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 1200, easing: 'easeOutQuart' },
        plugins: {
            legend: { labels: { color: '#8892a8', font: { family: 'Inter', size: 11 } } },
        },
        scales: {
            x: { grid: { color: 'rgba(255,255,255,0.04)' }, ticks: { color: '#8892a8', font: { size: 10 }, maxRotation: 45 } },
            y: { grid: { color: 'rgba(255,255,255,0.04)' }, ticks: { color: '#8892a8', font: { size: 10 } },
                 title: { display: true, text: yLabel, color: '#8892a8', font: { size: 11 } } },
        },
    };
}

function destroyCharts() {
    Object.values(charts).forEach(c => c && c.destroy());
    charts = {};
}

// ── FILTERS ──────────────────────────────────────────────────
function initEventListeners() {
    document.getElementById('btn-run-analysis').addEventListener('click', runAnalysis);
    document.getElementById('btn-reset-filters').addEventListener('click', resetFilters);
    document.getElementById('btn-export-csv').addEventListener('click', exportCSV);
    document.getElementById('filter-score').addEventListener('input', (e) => {
        document.getElementById('score-display').textContent = e.target.value;
        applyFilters();
    });
    document.getElementById('filter-highway').addEventListener('change', applyFilters);

    document.querySelectorAll('.tier-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            btn.classList.toggle('active');
            applyFilters();
        });
    });

    document.getElementById('modal-close').addEventListener('click', closeModal);
    document.querySelector('.modal-backdrop')?.addEventListener('click', closeModal);

    // Table sorting
    document.querySelectorAll('#sites-table th[data-sort]').forEach(th => {
        th.addEventListener('click', () => {
            const col = th.dataset.sort;
            if (sortCol === col) sortAsc = !sortAsc;
            else { sortCol = col; sortAsc = col === 'rank'; }
            applyFilters();
        });
    });
}

function applyFilters() {
    if (!analysisData) return;

    const minScore = parseInt(document.getElementById('filter-score').value) || 0;
    const highwayOnly = document.getElementById('filter-highway').checked;
    const activeTiers = [...document.querySelectorAll('.tier-btn.active')].map(b => parseInt(b.dataset.tier));
    const stateSelect = document.getElementById('filter-state');
    const selectedStates = [...stateSelect.selectedOptions].map(o => o.value).filter(Boolean);

    filteredSites = analysisData.sites.filter(s => {
        if (s.compositeScore < minScore) return false;
        if (activeTiers.length && !activeTiers.includes(s.tier)) return false;
        if (selectedStates.length && !selectedStates.includes(s.state)) return false;
        return true;
    });

    // Sort
    filteredSites.sort((a, b) => {
        let va = a[sortCol], vb = b[sortCol];
        if (sortCol === 'breakEvenMonths') { va = a.breakEven?.months || 999; vb = b.breakEven?.months || 999; }
        if (typeof va === 'string') return sortAsc ? va.localeCompare(vb) : vb.localeCompare(va);
        return sortAsc ? va - vb : vb - va;
    });

    updateTable(filteredSites);
    updateMap(filteredSites);
    updateCharts(filteredSites);
}

function resetFilters() {
    document.getElementById('filter-score').value = 0;
    document.getElementById('score-display').textContent = '0';
    document.getElementById('filter-highway').checked = true;
    document.querySelectorAll('.tier-btn').forEach(b => b.classList.add('active'));
    document.getElementById('filter-state').selectedIndex = 0;
    applyFilters();
}

function populateStateFilter(sites) {
    const states = [...new Set(sites.map(s => s.state))].sort();
    const select = document.getElementById('filter-state');
    select.innerHTML = '<option value="">All States</option>' +
        states.map(s => `<option value="${s}">${s}</option>`).join('');
}

// ── ANALYSIS ─────────────────────────────────────────────────
async function runAnalysis() {
    const btn = document.getElementById('btn-run-analysis');
    const overlay = document.getElementById('loading-overlay');
    const status = document.getElementById('loading-status');
    const fill = document.getElementById('progress-fill');

    btn.disabled = true;
    overlay.classList.remove('hidden');

    const steps = [
        'Fetching charger data from Open Charge Map...',
        'Querying OpenStreetMap for POIs...',
        'Running demand analysis...',
        'Computing competition density...',
        'Calculating accessibility scores...',
        'Evaluating power grid constraints...',
        'Building utilization forecasts...',
        'Running break-even calculations...',
        'Ranking top 50 locations...',
    ];

    let stepIdx = 0;
    const interval = setInterval(() => {
        stepIdx = Math.min(stepIdx + 1, steps.length - 1);
        status.textContent = steps[stepIdx];
        fill.style.width = `${((stepIdx + 1) / steps.length) * 90}%`;
    }, 2000);

    try {
        const resp = await fetch(`${API}/api/analysis/run`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({}),
        });

        if (!resp.ok) throw new Error(`Server error: ${resp.status}`);

        analysisData = await resp.json();
        fill.style.width = '100%';
        status.textContent = 'Analysis complete!';

        await new Promise(r => setTimeout(r, 500));

        updateKPIs(analysisData.summary);
        populateStateFilter(analysisData.sites);
        filteredSites = [...analysisData.sites];
        updateTable(filteredSites);
        updateMap(filteredSites);
        updateCharts(filteredSites);
        // Ensure map redraws properly after overlay closes
        setTimeout(() => map.invalidateSize(), 300);

    } catch (err) {
        console.error('Analysis failed:', err);
        status.textContent = `Error: ${err.message}. Check the server is running.`;
        fill.style.width = '0%';
        await new Promise(r => setTimeout(r, 3000));
    } finally {
        clearInterval(interval);
        overlay.classList.add('hidden');
        btn.disabled = false;
    }
}

// ── SITE DETAIL MODAL ────────────────────────────────────────
window.showSiteDetail = function (rank) {
    if (!analysisData) return;
    const site = analysisData.sites.find(s => s.rank === rank);
    if (!site) return;

    const be = site.breakEven || {};
    const forecast = site.utilizationForecast || [];
    const lastUtil = forecast.length ? forecast[forecast.length - 1].utilization : 0;

    document.getElementById('modal-body').innerHTML = `
        <h2>#${site.rank} ${site.city}</h2>
        <p class="subtitle">${site.state} · Tier ${site.tier} · Pop: ${formatNum(site.population)} · ${site.lat.toFixed(4)}°N, ${site.lng.toFixed(4)}°E</p>

        <div class="detail-grid">
            <div class="detail-item">
                <div class="label">Composite Score</div>
                <div class="value">${site.compositeScore.toFixed(1)} / 100</div>
            </div>
            <div class="detail-item">
                <div class="label">6-Month Utilization</div>
                <div class="value ${lastUtil >= 60 ? 'positive' : ''}">${lastUtil.toFixed(1)}%</div>
            </div>
            <div class="detail-item">
                <div class="label">Charger-to-Vehicle Ratio</div>
                <div class="value">${site.chargerToVehicleRatio.toFixed(4)}</div>
            </div>
            <div class="detail-item">
                <div class="label">Existing Chargers (${site.searchRadiusKm || 25}km)</div>
                <div class="value">${site.chargersInRadius}</div>
            </div>
            <div class="detail-item">
                <div class="label">Accessibility</div>
                <div class="value">${site.accessibilityLabel}</div>
            </div>
            <div class="detail-item" style="border-color: var(--accent-primary);">
                <div class="label" style="color: var(--accent-primary);">K-Means Market Tag</div>
                <div class="value">${site.kmeans_label || 'N/A'}</div>
            </div>
            <div class="detail-item" style="border-color: var(--accent-purple);">
                <div class="label" style="color: var(--accent-purple);">DBSCAN Outlier Status</div>
                <div class="value">${site.dbscan_label === 'Outlier / Anomaly' ? '<span style="color:var(--accent-danger)">Anomaly Detected</span>' : 'Standard Cluster Group'}</div>
            </div>
            <div class="detail-item">
                <div class="label">Break-Even</div>
                <div class="value ${be.months <= 24 ? 'positive' : be.months > 48 ? 'negative' : ''}">${be.months < 999 ? be.months + ' months' : 'N/A'}</div>
            </div>
            <div class="detail-item">
                <div class="label">Net Investment</div>
                <div class="value">₹${be.netInvestmentLakh?.toFixed(1)} L</div>
            </div>
            <div class="detail-item">
                <div class="label">Monthly Profit</div>
                <div class="value ${be.monthlyProfit > 0 ? 'positive' : 'negative'}">₹${formatNum(be.monthlyProfit || 0)}</div>
            </div>
        </div>

        <h4 style="color:var(--accent-primary);font-size:0.75rem;text-transform:uppercase;letter-spacing:0.04em;margin-bottom:8px;">Sub-Scores Breakdown</h4>
        <div class="detail-grid" style="grid-template-columns:repeat(5,1fr);">
            ${Object.entries(site.scores || {}).map(([k, v]) => `
                <div class="detail-item" style="text-align:center;">
                    <div class="label">${k}</div>
                    <div class="value" style="font-size:0.95rem;">${v.toFixed(1)}</div>
                </div>
            `).join('')}
        </div>

        <div class="mini-chart-container">
            <h4>Monthly Utilization Ramp-Up</h4>
            <canvas id="modal-chart" height="160"></canvas>
        </div>
    `;

    document.getElementById('site-modal').classList.remove('hidden');

    // Mini chart
    setTimeout(() => {
        const ctx = document.getElementById('modal-chart');
        if (ctx && forecast.length) {
            new Chart(ctx, {
                type: 'line',
                data: {
                    labels: forecast.map(f => f.monthName),
                    datasets: [
                        {
                            label: 'Utilization %',
                            data: forecast.map(f => f.utilization),
                            borderColor: '#00d4ff',
                            backgroundColor: '#00d4ff15',
                            fill: true,
                            tension: 0.4,
                            borderWidth: 2,
                            pointRadius: 5,
                            yAxisID: 'y',
                        },
                        {
                            label: 'Revenue (₹L)',
                            data: forecast.map(f => f.monthlyRevenueLakh),
                            borderColor: '#00ff88',
                            borderDash: [4, 4],
                            tension: 0.4,
                            borderWidth: 2,
                            pointRadius: 4,
                            yAxisID: 'y1',
                        },
                    ],
                },
                options: {
                    responsive: true,
                    animation: { duration: 800 },
                    plugins: { legend: { labels: { color: '#8892a8', font: { size: 10 } } } },
                    scales: {
                        x: { ticks: { color: '#8892a8' }, grid: { color: 'rgba(255,255,255,0.04)' } },
                        y: { position: 'left', title: { display: true, text: 'Utilization %', color: '#00d4ff' }, ticks: { color: '#8892a8' }, grid: { color: 'rgba(255,255,255,0.04)' } },
                        y1: { position: 'right', title: { display: true, text: 'Revenue ₹L', color: '#00ff88' }, ticks: { color: '#8892a8' }, grid: { display: false } },
                    },
                },
            });
        }
    }, 100);
};

function closeModal() {
    document.getElementById('site-modal').classList.add('hidden');
}

// ── EXPORT CSV ───────────────────────────────────────────────
function exportCSV() {
    if (!filteredSites.length) return;
    const headers = ['Rank', 'City', 'State', 'Latitude', 'Longitude', 'Composite Score',
        'Demand', 'Competition', 'Accessibility', 'Grid', 'Commercial', 'Search Radius km',
        'C:V Ratio', 'Chargers in 5km', 'Accessibility Label',
        'Break-Even Months', 'Net Investment Lakh', 'Monthly Revenue', 'Monthly Profit', 'ROI %'];

    const rows = filteredSites.map(s => {
        const be = s.breakEven || {};
        const sc = s.scores || {};
        return [s.rank, s.city, s.state, s.lat, s.lng, s.compositeScore.toFixed(2),
            sc.demand?.toFixed(2), sc.competition?.toFixed(2), sc.accessibility?.toFixed(2),
            sc.grid?.toFixed(2), sc.commercial?.toFixed(2),
            s.chargerToVehicleRatio.toFixed(6), s.chargersInRadius, s.searchRadiusKm || 25, s.accessibilityLabel,
            be.months, be.netInvestmentLakh?.toFixed(2), be.monthlyRevenue, be.monthlyProfit, be.roiPercent];
    });

    const csv = [headers, ...rows].map(r => r.join(',')).join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'ev_charger_top50_sites.csv';
    a.click();
    URL.revokeObjectURL(url);
}

// ── UTILS ────────────────────────────────────────────────────
function getLastUtil(site) {
    const f = site.utilizationForecast;
    return f && f.length ? f[f.length - 1].utilization.toFixed(1) : '—';
}

function formatNum(n) {
    if (n >= 10000000) return (n / 10000000).toFixed(1) + ' Cr';
    if (n >= 100000) return (n / 100000).toFixed(1) + ' L';
    if (n >= 1000) return (n / 1000).toFixed(1) + 'K';
    return n.toLocaleString('en-IN');
}

async function fetchCacheStatus() {
    try {
        const resp = await fetch(`${API}/api/cache/stats`);
        const data = await resp.json();
        const badge = document.getElementById('cache-indicator');
        badge.innerHTML = `<span class="dot"></span> L1:${data.l1_items} L2:${data.l2_items}`;
    } catch {
        // Server not running yet
    }
}
