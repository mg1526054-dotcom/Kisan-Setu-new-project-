const cropSelect = document.getElementById("crop-select");
const marketSelect = document.getElementById("market-select");
const dateInput = document.getElementById("date-select");
const scenarioSelect = document.getElementById("scenario-select");
const forecastBtn = document.getElementById("forecast-btn");
const resultSection = document.getElementById("result-section");
const emptyState = document.getElementById("empty-state");
const errorState = document.getElementById("error-state");
const mobileNavToggle = document.getElementById("mobile-nav-toggle");
const navMenu = document.getElementById("nav-menu");

let priceChart = null;

// Set default target date to 7 days in future
function defaultTargetDate() {
  const d = new Date();
  d.setDate(d.getDate() + 7);
  return d.toISOString().slice(0, 10);
}
if (dateInput) dateInput.value = defaultTargetDate();

// Mobile Navigation Toggle
if (mobileNavToggle && navMenu) {
  mobileNavToggle.addEventListener("click", () => {
    navMenu.classList.toggle("open");
  });
}

// Active Navigation Underline & Scrollspy Handler
const navLinks = document.querySelectorAll(".nav-link");

function setActiveNavLink(targetId) {
  navLinks.forEach(link => {
    if (link.getAttribute("href") === targetId) {
      link.classList.add("active");
    } else {
      link.classList.remove("active");
    }
  });
}

navLinks.forEach(link => {
  link.addEventListener("click", (e) => {
    const targetId = link.getAttribute("href");
    if (targetId && targetId.startsWith("#")) {
      setActiveNavLink(targetId);
      if (navMenu) navMenu.classList.remove("open");
    }
  });
});

// Detect Section Scrolling
const sections = document.querySelectorAll("section[id]");
window.addEventListener("scroll", () => {
  let currentSectionId = "#hero";
  const scrollPosition = window.scrollY + 140;

  sections.forEach(section => {
    const sectionTop = section.offsetTop;
    const sectionHeight = section.offsetHeight;
    if (scrollPosition >= sectionTop && scrollPosition < sectionTop + sectionHeight) {
      currentSectionId = "#" + section.getAttribute("id");
    }
  });

  if (currentSectionId) {
    setActiveNavLink(currentSectionId);
  }
});

// Fetch helper with error handling
async function fetchJSON(url, options) {
  const res = await fetch(url, options);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed: ${res.status}`);
  }
  return res.json();
}

async function loadCrops() {
  const crops = await fetchJSON("/api/crops");
  cropSelect.innerHTML = crops.map(c => `<option value="${c.id}">${c.name}</option>`).join("");
  if (crops.length) await loadMarkets(crops[0].name);
}

async function loadMarkets(cropName) {
  const markets = await fetchJSON(`/api/markets?crop=${encodeURIComponent(cropName)}`);
  marketSelect.innerHTML = markets.map(m => `<option value="${m.id}">${m.name} (${m.district})</option>`).join("");
}

cropSelect.addEventListener("change", async () => {
  const selectedName = cropSelect.options[cropSelect.selectedIndex].text;
  await loadMarkets(selectedName);
});

function showError(message) {
  errorState.textContent = message;
  errorState.classList.remove("hidden");
  resultSection.classList.add("hidden");
  emptyState.classList.add("hidden");
}

function animateNumber(elementId, start, end, duration = 800) {
  const obj = document.getElementById(elementId);
  if (!obj) return;
  let startTimestamp = null;
  const step = (timestamp) => {
    if (!startTimestamp) startTimestamp = timestamp;
    const progress = Math.min((timestamp - startTimestamp) / duration, 1);
    const easeProgress = 1 - Math.pow(1 - progress, 3);
    const value = Math.floor(easeProgress * (end - start) + start);
    obj.textContent = value.toLocaleString();
    if (progress < 1) {
      window.requestAnimationFrame(step);
    } else {
      obj.textContent = Math.round(end).toLocaleString();
    }
  };
  window.requestAnimationFrame(step);
}

function renderDrivers(drivers) {
  const list = document.getElementById("drivers-list");
  if (!list) return;
  
  const upIcon = `
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
      <polyline points="18 15 12 9 6 15"></polyline>
    </svg>`;
    
  const downIcon = `
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
      <polyline points="6 9 12 15 18 9"></polyline>
    </svg>`;

  list.innerHTML = drivers.map(d => {
    const isUp = d.direction === 'upward';
    return `
      <li>
        <div class="driver-icon-badge ${isUp ? 'up' : 'down'}">
          ${isUp ? upIcon : downIcon}
        </div>
        <span>${d.sentence}</span>
      </li>
    `;
  }).join("");
}

function renderMetrics(metrics) {
  const grid = document.getElementById("metrics-grid");
  if (!grid) return;
  const items = [
    { label: "Model MAE", value: `₹${metrics.model_mae}` },
    { label: "Model MAPE", value: `${metrics.model_mape_pct}%` },
    { label: "Range Coverage", value: `${metrics.range_coverage_pct}%` },
    { label: "Baseline MAE", value: `₹${metrics.baseline_mae}` },
    { label: "Baseline MAPE", value: `${metrics.baseline_mape_pct}%` },
    { label: "Test Samples", value: metrics.n_test },
  ];
  grid.innerHTML = items.map(i => `
    <div class="metric-box">
      <div class="value">${i.value}</div>
      <div class="label">${i.label}</div>
    </div>
  `).join("");
}

async function renderChart(cropId, marketId) {
  const history = await fetchJSON(`/api/history?crop_id=${cropId}&market_id=${marketId}`);
  const recent = history.slice(-52);
  const labels = recent.map(h => h.date);
  const modal = recent.map(h => h.modal_price);
  const min = recent.map(h => h.min_price);
  const max = recent.map(h => h.max_price);

  const canvas = document.getElementById("price-chart");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");

  const gradientModal = ctx.createLinearGradient(0, 0, 0, 260);
  gradientModal.addColorStop(0, "rgba(44, 110, 73, 0.32)");
  gradientModal.addColorStop(0.8, "rgba(44, 110, 73, 0.03)");
  gradientModal.addColorStop(1, "rgba(44, 110, 73, 0.0)");

  if (priceChart) priceChart.destroy();
  
  priceChart = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "Modal Price",
          data: modal,
          borderColor: "#2C6E49",
          borderWidth: 2.5,
          backgroundColor: gradientModal,
          fill: true,
          tension: 0.35,
          pointRadius: 0,
          pointHoverRadius: 6,
          pointHoverBackgroundColor: "#2C6E49",
          pointHoverBorderColor: "#FFFFFF",
          pointHoverBorderWidth: 2
        },
        {
          label: "Daily High",
          data: max,
          borderColor: "#D97706",
          borderWidth: 1.5,
          borderDash: [4, 4],
          pointRadius: 0,
          tension: 0.2
        },
        {
          label: "Daily Low",
          data: min,
          borderColor: "#84C59E",
          borderWidth: 1.5,
          borderDash: [4, 4],
          pointRadius: 0,
          tension: 0.2
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: {
        mode: 'index',
        intersect: false,
      },
      plugins: {
        legend: {
          position: "bottom",
          labels: {
            boxWidth: 12,
            boxHeight: 12,
            usePointStyle: true,
            pointStyle: 'circle',
            font: { family: "'Inter', sans-serif", size: 12, weight: '500' },
            padding: 16
          }
        },
        tooltip: {
          backgroundColor: "#19382C",
          titleFont: { family: "'Inter', sans-serif", size: 13, weight: "700" },
          bodyFont: { family: "'Inter', sans-serif", size: 12 },
          padding: 12,
          cornerRadius: 8,
          callbacks: {
            label: function(context) {
              let label = context.dataset.label || '';
              if (label) label += ': ';
              if (context.parsed.y !== null) {
                label += `₹${context.parsed.y.toLocaleString()}/qt`;
              }
              return label;
            }
          }
        }
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: { maxTicksLimit: 8, font: { family: "'Inter', sans-serif", size: 11 }, color: "#6B7C70" }
        },
        y: {
          grid: { color: "rgba(0, 0, 0, 0.05)" },
          ticks: {
            callback: v => `₹${v.toLocaleString()}`,
            font: { family: "'Inter', sans-serif", size: 11 },
            color: "#6B7C70"
          }
        },
      },
    },
  });
}

async function getForecast() {
  errorState.classList.add("hidden");
  emptyState.classList.add("hidden");
  resultSection.classList.add("hidden");

  forecastBtn.disabled = true;
  forecastBtn.innerHTML = `
    <span class="btn-text">Forecasting…</span>
    <svg class="btn-icon spinner" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
      <path d="M21 12a9 9 0 1 1-6.219-8.56"/>
    </svg>
  `;

  try {
    const cropId = parseInt(cropSelect.value, 10);
    const marketId = parseInt(marketSelect.value, 10);
    const targetDate = dateInput.value;
    const scenario = scenarioSelect ? scenarioSelect.value : "normal";

    const forecast = await fetchJSON("/api/forecast", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        crop_id: cropId,
        market_id: marketId,
        target_date: targetDate,
        geopolitical_scenario: scenario
      }),
    });

    // Update Risk Badge
    const riskTag = document.getElementById("risk-tag");
    if (riskTag) {
      riskTag.innerHTML = `
        <svg class="tag-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
        </svg>
        Risk: ${forecast.risk_level}`;
    }

    // Update Confidence Gauge Bar
    const confPct = Math.round(forecast.confidence * 100);
    const confText = document.getElementById("confidence-text");
    if (confText) confText.textContent = `Confidence ${confPct}%`;
    const confFill = document.getElementById("confidence-gauge-fill");
    if (confFill) confFill.style.width = `${confPct}%`;

    // Forecast Label & Advisory
    document.getElementById("forecast-label").textContent =
      `Predicted price for ${forecast.crop} at ${forecast.market}, week of ${forecast.target_date}`;
    document.getElementById("advisory-text").textContent = forecast.advisory;
    document.getElementById("disclaimer-text").textContent = forecast.disclaimer;

    // Render Geopolitical Disruption Note if present
    const geoBox = document.getElementById("geopolitical-box");
    const geoText = document.getElementById("geopolitical-text");
    if (forecast.geopolitical_note) {
      if (geoText) geoText.textContent = forecast.geopolitical_note;
      if (geoBox) geoBox.classList.remove("hidden");
    } else {
      if (geoBox) geoBox.classList.add("hidden");
    }

    // Render Drivers & Metrics
    renderDrivers(forecast.drivers);
    renderMetrics(forecast.model_metrics);

    // Reveal Results Section
    resultSection.classList.remove("hidden");
    resultSection.scrollIntoView({ behavior: 'smooth', block: 'start' });

    // Animate Count-Up for predicted price range
    animateNumber("predicted-min-val", 0, forecast.predicted_min);
    animateNumber("predicted-max-val", 0, forecast.predicted_max);

    // Render 52-week price trend chart
    await renderChart(cropId, marketId);

  } catch (err) {
    showError(err.message || "Something went wrong while generating the forecast.");
  } finally {
    forecastBtn.disabled = false;
    forecastBtn.innerHTML = `
      <span class="btn-text">Get forecast</span>
      <svg class="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
        <line x1="5" y1="12" x2="19" y2="12"></line>
        <polyline points="12 5 19 12 12 19"></polyline>
      </svg>
    `;
  }
}

forecastBtn.addEventListener("click", getForecast);

loadCrops().catch(err => showError(err.message));
