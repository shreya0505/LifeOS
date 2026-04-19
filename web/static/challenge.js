// Hard 90 Challenge — client helpers.

window.chEmberBurst = function () {
  const host = document.getElementById("ch-ember-burst");
  if (!host) return;
  const rect = host.getBoundingClientRect();
  const cx = rect.width / 2;
  const cy = rect.height / 2;
  for (let i = 0; i < 40; i++) {
    const e = document.createElement("div");
    e.className = "ch-ember";
    const angle = Math.random() * Math.PI * 2;
    const dist = 120 + Math.random() * 160;
    e.style.left = cx + "px";
    e.style.top = cy + "px";
    e.style.setProperty("--dx", Math.cos(angle) * dist + "px");
    e.style.setProperty("--dy", Math.sin(angle) * dist - 100 + "px");
    e.style.animationDelay = Math.random() * 0.4 + "s";
    host.appendChild(e);
    setTimeout(() => e.remove(), 2500);
  }
};

window.chSealCeremony = function (btn) {
  if (!btn || btn.dataset.sealing === "1" || btn.disabled) return false;
  btn.dataset.sealing = "1";
  const txt = btn.textContent || "";
  const m = txt.match(/Day\s+(\d+)/i);
  const day = m ? m[1] : "";
  const stamp = document.createElement("div");
  stamp.className = "ch-seal-stamp";
  stamp.innerHTML =
    '<div class="ch-seal-stamp__disc">' +
    '<span class="ch-seal-stamp__glyph">◈</span>' +
    '<span class="ch-seal-stamp__day">' + day + '</span>' +
    '<span class="ch-seal-stamp__lbl">sealed</span>' +
    '</div>';
  document.body.appendChild(stamp);
  setTimeout(() => stamp.remove(), 700);
  return true;
};

document.addEventListener("submit", function (ev) {
  const form = ev.target;
  if (!form.matches(".ch-seal-form")) return;
  const btn = form.querySelector(".ch-btn-seal");
  if (!btn || btn.disabled) return;
  if (btn.classList.contains("is-sealing")) return;
  ev.preventDefault();
  if (window.chSealCeremony(btn)) {
    setTimeout(() => form.submit(), 650);
  } else {
    form.submit();
  }
}, true);

window.chEmberDrift = function () {
  const host = document.getElementById("ch-ember-drift");
  if (!host) return;
  const count = 7;
  for (let i = 0; i < count; i++) {
    const e = document.createElement("div");
    e.className = "ch-ember-d";
    e.style.left = (15 + Math.random() * 70) + "%";
    e.style.bottom = (Math.random() * 20) + "%";
    const dur = 3.5 + Math.random() * 2.5;
    e.style.animationDuration = dur + "s";
    e.style.animationDelay = (Math.random() * 1.2) + "s";
    host.appendChild(e);
  }
};

window.chAshRain = function () {
  const host = document.getElementById("ch-ash-field");
  if (!host) return;
  for (let i = 0; i < 80; i++) {
    const a = document.createElement("div");
    a.className = "ch-ash";
    a.style.left = Math.random() * 100 + "%";
    const dur = 4 + Math.random() * 6;
    a.style.animationDuration = dur + "s";
    a.style.animationDelay = Math.random() * 4 + "s";
    host.appendChild(a);
  }
};

// ═══════════════════ METRICS v2 ═══════════════════

const CH_REDUCED_MOTION = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

function chParseJSONAttr(el, name) {
  const raw = el.getAttribute(name);
  if (!raw) return null;
  try { return JSON.parse(raw); } catch (e) { return null; }
}

function chRankColor(r) {
  // 1 = red (miss), 5 = green (held)
  if (r == null) return "#3a2828";
  const stops = ["#d4383a", "#d66a3a", "#d6a93a", "#9ac93f", "#4fbf6a"];
  const i = Math.max(0, Math.min(4, Math.round(r) - 1));
  return stops[i];
}

function chHeatColor(avg) {
  if (avg == null) return "#2a1e1e";
  const t = Math.max(0, Math.min(1, (avg - 1) / 4));
  const stops = [
    [212, 56, 58], [214, 106, 58], [214, 169, 58], [154, 201, 63], [79, 191, 106]
  ];
  const pos = t * (stops.length - 1);
  const i = Math.floor(pos);
  const f = pos - i;
  const a = stops[i];
  const b = stops[Math.min(stops.length - 1, i + 1)];
  const mix = a.map((v, k) => Math.round(v + (b[k] - v) * f));
  return `rgb(${mix[0]}, ${mix[1]}, ${mix[2]})`;
}

function chCountUp(el) {
  const target = parseFloat(el.dataset.target);
  if (!isFinite(target)) return;
  const decimals = parseInt(el.dataset.decimals || "0", 10);
  const sign = el.dataset.sign === "true";
  const fmt = (v) => {
    const s = v.toFixed(decimals);
    if (sign && v > 0) return "+" + s;
    return s;
  };
  if (CH_REDUCED_MOTION) { el.textContent = fmt(target); return; }
  const duration = 1200;
  const start = performance.now();
  const from = 0;
  function tick(now) {
    const t = Math.min(1, (now - start) / duration);
    const eased = 1 - Math.pow(1 - t, 3);
    el.textContent = fmt(from + (target - from) * eased);
    if (t < 1) requestAnimationFrame(tick);
    else el.textContent = fmt(target);
  }
  requestAnimationFrame(tick);
}

function chRevealOnScroll(root) {
  const spreads = root.querySelectorAll("[data-reveal]");
  if (!("IntersectionObserver" in window) || CH_REDUCED_MOTION) {
    spreads.forEach(s => {
      s.classList.add("is-revealed");
      s.querySelectorAll(".ch-count").forEach(chCountUp);
    });
    return;
  }
  const seen = new WeakSet();
  const io = new IntersectionObserver((entries) => {
    entries.forEach(e => {
      if (e.isIntersecting && !seen.has(e.target)) {
        seen.add(e.target);
        e.target.classList.add("is-revealed");
        e.target.querySelectorAll(".ch-count").forEach(chCountUp);
      }
    });
  }, { threshold: 0.05, rootMargin: "0px 0px -10% 0px" });
  spreads.forEach(s => io.observe(s));
}

function chMovingAvg(values, win) {
  const out = [];
  for (let i = 0; i < values.length; i++) {
    const start = Math.max(0, i - win + 1);
    const slice = values.slice(start, i + 1).filter(v => v != null);
    if (!slice.length) { out.push(null); continue; }
    out.push(slice.reduce((a, b) => a + b, 0) / slice.length);
  }
  return out;
}

const CH_TOOLTIP_THEME = {
  backgroundColor: "#12090a",
  titleColor: "#f4d9b4",
  titleFont: { family: "'JetBrains Mono', monospace", weight: "700", size: 11 },
  bodyColor: "#e8d4b8",
  bodyFont: { family: "'JetBrains Mono', monospace", size: 11 },
  borderColor: "#d4383a",
  borderWidth: 1,
  padding: 10,
  cornerRadius: 2,
  displayColors: false,
};

function chRenderPulseChart(canvas, series) {
  if (!canvas || !window.Chart || !series || series.length < 2) return;
  const labels = series.map(p => p.date);
  const values = series.map(p => p.avg_rank);
  const ma = chMovingAvg(values, 7);
  const ctx = canvas.getContext("2d");
  const segColor = (c) => {
    const v = c.p1.parsed.y;
    return chRankColor(v);
  };
  const pointColors = values.map(v => chRankColor(v));
  new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "Daily quality",
          data: values,
          borderColor: "#8a6b5a",
          backgroundColor: (ctx) => {
            const chart = ctx.chart;
            const { ctx: c, chartArea } = chart;
            if (!chartArea) return "rgba(138,107,90,0.08)";
            const g = c.createLinearGradient(0, chartArea.top, 0, chartArea.bottom);
            g.addColorStop(0, "rgba(79,191,106,0.22)");
            g.addColorStop(0.5, "rgba(214,169,58,0.12)");
            g.addColorStop(1, "rgba(212,56,58,0.22)");
            return g;
          },
          segment: { borderColor: segColor },
          pointBackgroundColor: pointColors,
          pointBorderColor: pointColors,
          fill: true,
          tension: 0.3,
          pointRadius: 3,
          pointHoverRadius: 6,
          borderWidth: 2.5,
        },
        {
          label: "7-day avg",
          data: ma,
          borderColor: "#f4d9b4",
          borderDash: [4, 4],
          fill: false,
          tension: 0.3,
          pointRadius: 0,
          borderWidth: 2,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        y: {
          min: 1, max: 5,
          ticks: { color: "#8a6b5a", font: { family: "'JetBrains Mono', monospace", size: 10 } },
          grid: { color: "rgba(138, 107, 90, 0.12)" },
        },
        x: {
          ticks: { color: "#8a6b5a", font: { family: "'JetBrains Mono', monospace", size: 10 }, maxTicksLimit: 8 },
          grid: { display: false },
        },
      },
      plugins: {
        legend: { labels: { color: "#c8a888", font: { family: "'JetBrains Mono', monospace", size: 11 } } },
        tooltip: {
          ...CH_TOOLTIP_THEME,
          callbacks: {
            label: (ctx) => `${ctx.dataset.label}: ${ctx.parsed.y == null ? "—" : ctx.parsed.y.toFixed(2)}`,
          },
        },
      },
    },
  });
}

function chRenderEngagementChart(canvas, weeks) {
  if (!canvas || !window.Chart || !weeks || !weeks.length) return;
  const ctx = canvas.getContext("2d");
  new Chart(ctx, {
    type: "bar",
    data: {
      labels: weeks.map(w => w.week),
      datasets: [{
        label: "Notes ratio",
        data: weeks.map(w => w.ratio),
        backgroundColor: "#d4383a",
        borderRadius: 1,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        y: { min: 0, max: 1, display: false },
        x: { ticks: { color: "#8a6b5a", font: { size: 9 } }, grid: { display: false } },
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          ...CH_TOOLTIP_THEME,
          callbacks: {
            label: (c) => `${(c.parsed.y * 100).toFixed(0)}% notes`,
          },
        },
      },
    },
  });
}

function chRenderSparklines(root) {
  root.querySelectorAll(".ch-task-spark[data-spark]").forEach(host => {
    const data = chParseJSONAttr(host, "data-spark");
    if (!data || !data.length) return;
    const W = 86, H = 22, pad = 1;
    const n = data.length;
    const step = (W - pad * 2) / Math.max(1, n);
    const ns = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(ns, "svg");
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    svg.setAttribute("width", W);
    svg.setAttribute("height", H);
    for (let i = 0; i < n; i++) {
      const v = data[i];
      const h = v == null ? 2 : Math.max(2, (v / 5) * (H - pad * 2));
      const x = pad + i * step;
      const rect = document.createElementNS(ns, "rect");
      rect.setAttribute("x", x);
      rect.setAttribute("y", H - pad - h);
      rect.setAttribute("width", Math.max(1, step - 1));
      rect.setAttribute("height", h);
      rect.setAttribute("fill", chRankColor(v));
      rect.setAttribute("rx", "0.5");
      svg.appendChild(rect);
    }
    host.appendChild(svg);
  });
}

const CH_DOW_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

function chRenderHeatmap(host, weekday) {
  if (!host || !weekday) return;
  host.innerHTML = "";
  weekday.forEach(row => {
    const cell = document.createElement("div");
    cell.className = "ch-heatmap-cell";
    cell.style.background = chHeatColor(row.avg);
    cell.title = `${CH_DOW_LABELS[row.dow]} · avg ${row.avg == null ? "—" : row.avg.toFixed(2)} · ${row.n} samples`;
    const lbl = document.createElement("span");
    lbl.className = "ch-heatmap-lbl";
    lbl.textContent = CH_DOW_LABELS[row.dow];
    const val = document.createElement("span");
    val.className = "ch-heatmap-val";
    val.textContent = row.avg == null ? "—" : row.avg.toFixed(1);
    cell.appendChild(lbl);
    cell.appendChild(val);
    host.appendChild(cell);
  });
}

function chRenderArcRail(host, rail, daysElapsed, daysTotal, peakLevel) {
  if (!host || !rail || !rail.length) return;
  host.innerHTML = "";
  const curPct = Math.min(100, (daysElapsed / daysTotal) * 100);
  const peakIdx = (peakLevel != null && peakLevel > 0) ? Math.min(rail.length - 1, peakLevel - 1) : -1;

  const track = document.createElement("div");
  track.className = "ch-arc-track";

  const bar = document.createElement("div");
  bar.className = "ch-arc-bar";
  const fill = document.createElement("div");
  fill.className = "ch-arc-fill";
  fill.style.width = `${curPct}%`;
  bar.appendChild(fill);
  track.appendChild(bar);

  const pin = document.createElement("div");
  pin.className = "ch-arc-pin";
  pin.style.left = `${curPct}%`;
  pin.setAttribute("data-label", `DAY ${daysElapsed}`);
  pin.title = `Current · day ${daysElapsed}`;
  track.appendChild(pin);

  if (peakIdx >= 0) {
    const peakTier = rail[peakIdx];
    const peakPct = Math.min(100, (peakTier.day_end / daysTotal) * 100);
    const peakPin = document.createElement("div");
    peakPin.className = "ch-arc-pin ch-arc-pin-peak";
    peakPin.style.left = `${peakPct}%`;
    peakPin.setAttribute("data-label", "PEAK");
    peakPin.title = `Peak · ${peakTier.name}`;
    track.appendChild(peakPin);
  }

  host.appendChild(track);

  const tiers = document.createElement("ol");
  tiers.className = "ch-arc-tiers";
  rail.forEach((tier, i) => {
    const reached = (i < peakIdx) || (i === peakIdx);
    const current = (daysElapsed > tier.day_start && daysElapsed <= tier.day_end);
    const li = document.createElement("li");
    li.className = "ch-arc-tier";
    if (reached) li.classList.add("is-reached");
    if (current) li.classList.add("is-current");
    li.title = `${tier.name} · day ${tier.day_start + 1}–${tier.day_end}`;
    li.innerHTML = `
      <span class="ch-arc-tier-idx">${String(i + 1).padStart(2, "0")}</span>
      <span class="ch-arc-tier-name">${tier.name}</span>
      <span class="ch-arc-tier-days">d${tier.day_start + 1}–${tier.day_end}</span>
    `;
    tiers.appendChild(li);
  });
  host.appendChild(tiers);
}

function chInitMetrics() {
  const root = document.querySelector("[data-metrics]");
  if (!root) return;
  const quality = chParseJSONAttr(root, "data-quality");
  const weekday = chParseJSONAttr(root, "data-weekday");
  const engagement = chParseJSONAttr(root, "data-engagement");
  const tierRail = chParseJSONAttr(root, "data-tier-rail");
  const daysElapsed = parseInt(root.dataset.daysElapsed || "0", 10);
  const daysTotal = parseInt(root.dataset.daysTotal || "90", 10);
  const peakLevel = parseInt(root.dataset.peakLevel || "0", 10);

  chRenderPulseChart(document.getElementById("ch-chart-pulse"), quality);
  chRenderEngagementChart(document.getElementById("ch-chart-engagement"), engagement);
  chRenderSparklines(root);
  chRenderHeatmap(document.getElementById("ch-heatmap"), weekday);
  chRenderArcRail(document.getElementById("ch-arc-rail"), tierRail, daysElapsed, daysTotal, peakLevel);
  chRevealOnScroll(root);
}

document.addEventListener("DOMContentLoaded", () => {
  if (document.getElementById("ch-ember-burst")) window.chEmberBurst();
  if (document.getElementById("ch-ash-field")) window.chAshRain();
  chInitMetrics();
});
