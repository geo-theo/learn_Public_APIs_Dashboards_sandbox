const numberFormat = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
const dateFormat = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric" });
const dateTimeFormat = new Intl.DateTimeFormat("en-US", {
  month: "short", day: "numeric", hour: "numeric", minute: "2-digit"
});

let visitationChart;
let map;
let mapLayer;

async function getJson(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return response.json();
}

function showError(error) {
  console.error(error);
  document.getElementById("refresh-message").textContent = `Error: ${error.message}`;
}

async function loadSummary() {
  const data = await getJson("/api/summary");
  document.getElementById("weighted-visits").textContent = numberFormat.format(data.weighted_visits);
  document.getElementById("valid-records").textContent = numberFormat.format(data.valid_records);
  document.getElementById("invalid-records").textContent = numberFormat.format(data.invalid_records);
  document.getElementById("active-alerts").textContent = numberFormat.format(data.active_weather_alerts);
  if (data.window_start && data.window_end) {
    document.getElementById("visit-window").textContent =
      `${dateFormat.format(new Date(`${data.window_start}T12:00:00`))} to ` +
      `${dateFormat.format(new Date(`${data.window_end}T12:00:00`))}`;
  }
}

async function loadParks() {
  const parks = await getJson("/api/parks");
  const select = document.getElementById("park-filter");
  parks.forEach((park) => {
    const option = document.createElement("option");
    option.value = park.code;
    option.textContent = park.name;
    select.appendChild(option);
  });
  return parks;
}

async function loadVisitation() {
  const days = document.getElementById("days-filter").value;
  const metric = document.getElementById("metric-filter").value;
  const park = document.getElementById("park-filter").value;
  const params = new URLSearchParams({ days, metric, group_by: "day" });
  if (park) params.set("park_code", park);
  const result = await getJson(`/api/visitation?${params}`);
  const context = document.getElementById("visitation-chart");

  if (visitationChart) visitationChart.destroy();
  visitationChart = new Chart(context, {
    type: "line",
    data: {
      labels: result.data.map((row) => row.date),
      datasets: [{
        label: metric === "weighted" ? "Weighted visits" : "Raw visits",
        data: result.data.map((row) => row.value),
        borderColor: "#174c3c",
        backgroundColor: "rgba(23, 76, 60, .12)",
        borderWidth: 2,
        pointRadius: 0,
        pointHoverRadius: 4,
        fill: true,
        tension: .22
      }]
    },
    options: {
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      scales: {
        x: { grid: { display: false }, ticks: { maxTicksLimit: 8 } },
        y: { beginAtZero: true, grid: { color: "#e7e2d8" } }
      },
      plugins: { legend: { display: false } }
    }
  });
}

async function loadForecasts() {
  const rows = await getJson("/api/weather/forecast?periods_per_park=1");
  const container = document.getElementById("forecast-list");
  if (!rows.length) {
    container.className = "forecast-list empty-state";
    container.textContent = "Run a refresh to load live NWS forecasts.";
    return;
  }
  container.className = "forecast-list";
  container.innerHTML = rows.map((row) => `
    <article class="forecast-card">
      <div class="forecast-card__top">
        <strong>${row.park_name}</strong>
        <span class="forecast-card__temp">${row.temperature_f ?? "--"} F</span>
      </div>
      <p>${row.short_forecast}<br>
      Precipitation: ${row.precipitation_probability ?? 0}% | Wind: ${row.wind_speed ?? "n/a"}</p>
    </article>
  `).join("");
}

async function loadStreamflow() {
  const rows = await getJson("/api/streamflow/latest");
  const body = document.getElementById("streamflow-table");
  if (!rows.length) {
    body.innerHTML = '<tr><td colspan="3" class="empty-state">Run a refresh to load USGS data.</td></tr>';
    return rows;
  }
  body.innerHTML = rows.map((row) => `
    <tr>
      <td>${row.name}</td>
      <td>${numberFormat.format(row.discharge_cfs)} cfs</td>
      <td>${dateTimeFormat.format(new Date(row.observed_at))}</td>
    </tr>
  `).join("");
  return rows;
}

function initializeMap(parks, gauges) {
  if (!window.L) return;
  if (!map) {
    map = L.map("conditions-map", { scrollWheelZoom: false }).setView([47.0, -110.7], 5);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 18,
      attribution: "&copy; OpenStreetMap contributors"
    }).addTo(map);
  }
  if (mapLayer) mapLayer.remove();
  mapLayer = L.layerGroup().addTo(map);
  parks.forEach((park) => {
    L.circleMarker([park.latitude, park.longitude], {
      radius: 7, color: "#174c3c", fillColor: "#2d7a62", fillOpacity: .9, weight: 2
    }).bindPopup(`<strong>${park.name}</strong><br>${park.region}`).addTo(mapLayer);
  });
  gauges.forEach((gauge) => {
    L.circleMarker([gauge.latitude, gauge.longitude], {
      radius: 6, color: "#9a431d", fillColor: "#de6b35", fillOpacity: .9, weight: 2
    }).bindPopup(
      `<strong>${gauge.name}</strong><br>${numberFormat.format(gauge.discharge_cfs)} cfs`
    ).addTo(mapLayer);
  });
}

async function loadQuality() {
  const rows = await getJson("/api/quality/latest");
  const container = document.getElementById("quality-list");
  if (!rows.length) {
    container.className = "status-list empty-state";
    container.textContent = "Run the QA command to populate checks.";
    return;
  }
  container.className = "status-list";
  container.innerHTML = rows.map((row) => `
    <div class="status-row">
      <strong>${row.check_name.replaceAll("_", " ")}</strong>
      <span class="status ${row.passed ? "status--ok" : "status--bad"}">
        ${row.passed ? "Pass" : row.severity}
      </span>
      <span class="status-detail">${row.failed_rows} failed row${row.failed_rows === 1 ? "" : "s"}</span>
    </div>
  `).join("");
}

async function loadRuns() {
  const rows = await getJson("/api/pipeline-runs?limit=7");
  const container = document.getElementById("pipeline-list");
  if (!rows.length) {
    container.className = "status-list empty-state";
    container.textContent = "Run a pipeline command to populate the log.";
    return;
  }
  container.className = "status-list";
  container.innerHTML = rows.map((row) => `
    <div class="status-row">
      <strong>${row.source}</strong>
      <span class="status status--${row.status === "success" ? "ok" : row.status === "running" ? "running" : "bad"}">
        ${row.status}
      </span>
      <span class="status-detail">${numberFormat.format(row.rows_loaded)} rows loaded</span>
    </div>
  `).join("");
}

async function loadDashboard() {
  try {
    const parksPromise = loadParks();
    const streamflowPromise = loadStreamflow();
    const [parks, gauges] = await Promise.all([parksPromise, streamflowPromise]);
    initializeMap(parks, gauges);
    await Promise.all([loadSummary(), loadVisitation(), loadForecasts(), loadQuality(), loadRuns()]);
  } catch (error) {
    showError(error);
  }
}

for (const id of ["park-filter", "days-filter", "metric-filter"]) {
  document.getElementById(id).addEventListener("change", () => loadVisitation().catch(showError));
}

document.getElementById("refresh-pipeline").addEventListener("click", async (event) => {
  const button = event.currentTarget;
  const message = document.getElementById("refresh-message");
  button.disabled = true;
  message.textContent = "Fetching and validating public data...";
  try {
    const result = await getJson("/api/admin/refresh", { method: "POST" });
    message.textContent = Object.entries(result.sources)
      .map(([source, status]) => `${source}: ${status}`)
      .join(" | ");
    await loadDashboard();
  } catch (error) {
    showError(error);
  } finally {
    button.disabled = false;
  }
});

loadDashboard();
