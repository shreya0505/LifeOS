(function () {
  const chartDefaults = {
    fontFamily: "Manrope, system-ui, sans-serif",
    foreColor: "rgba(245,241,234,0.68)",
    toolbar: { show: false },
    animations: { enabled: true, speed: 420 },
  };

  function cssVar(name, fallback) {
    const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return value || fallback;
  }

  function palette() {
    return {
      brass: cssVar("--saga-brass", "#CF9D7B"),
      champagne: cssVar("--saga-champagne", "#EACEAA"),
      text: cssVar("--saga-text", "#F5F1EA"),
      muted: "rgba(245,241,234,0.58)",
      line: "rgba(234,206,170,0.14)",
      dim: cssVar("--saga-dim", "#162127"),
      danger: cssVar("--saga-error", "#E27F6F"),
    };
  }

  function payloadFor(root, explicitWindow) {
    const id = root.dataset.payloadId || (explicitWindow ? `saga-payload-${explicitWindow}` : "");
    const script = id ? root.querySelector(`#${id}`) : root.querySelector('script[type="application/json"]');
    if (!script) return null;
    try {
      return JSON.parse(script.textContent);
    } catch (_) {
      return null;
    }
  }

  function destroyChart(el) {
    if (el && el._sagaChart) {
      el._sagaChart.destroy();
      el._sagaChart = null;
      el.innerHTML = "";
    }
  }

  function render(root, selector, options) {
    const el = root.querySelector(selector);
    if (!el || !window.ApexCharts) return;
    destroyChart(el);
    const chart = new ApexCharts(el, options);
    el._sagaChart = chart;
    chart.render();
  }

  function baseChart(type, height) {
    const p = palette();
    return {
      chart: { ...chartDefaults, type, height, background: "transparent" },
      grid: { borderColor: p.line, strokeDashArray: 4 },
      tooltip: { theme: "dark" },
      legend: { labels: { colors: p.muted }, markers: { radius: 2 } },
      dataLabels: { enabled: false },
      stroke: { curve: "smooth", width: 2 },
    };
  }

  function initKpis(root, data) {
    const p = palette();
    Object.entries(data.headline.kpis || {}).forEach(([key, kpi]) => {
      const tile = root.querySelector(`[data-kpi="${key}"] .saga-kpi-tile__spark`);
      if (!tile || !window.ApexCharts) return;
      destroyChart(tile);
      const chart = new ApexCharts(tile, {
        chart: { type: "area", height: 58, sparkline: { enabled: true }, animations: { enabled: false } },
        series: [{ data: kpi.spark || [] }],
        stroke: { curve: "smooth", width: 2, colors: [p.champagne] },
        fill: {
          type: "gradient",
          gradient: { opacityFrom: 0.34, opacityTo: 0.02, stops: [0, 100] },
          colors: [p.brass],
        },
        tooltip: { enabled: false },
      });
      tile._sagaChart = chart;
      chart.render();
    });
  }

  function initComove(root, data) {
    const p = palette();
    render(root, "#chart-comove", {
      ...baseChart("line", 340),
      series: [
        { name: "Mood load", type: "area", data: data.timeseries.mood_load },
        { name: "Output index", type: "line", data: data.timeseries.output_index },
      ],
      colors: [p.danger, p.champagne],
      labels: data.timeseries.labels,
      yaxis: { min: 0, max: 100 },
      fill: { type: ["gradient", "solid"], opacity: [0.24, 1] },
    });
  }

  function initAffect(root, data) {
    render(root, "#chart-affect", {
      ...baseChart("line", 300),
      series: [
        { name: "Energy", data: data.timeseries.avg_energy },
        { name: "Pleasantness", data: data.timeseries.avg_pleasantness },
      ],
      colors: ["#F4C430", "#5BB97C"],
      labels: data.timeseries.labels,
      yaxis: { min: -5, max: 5, tickAmount: 10 },
      annotations: {
        yaxis: [{ y: 0, borderColor: "rgba(245,241,234,0.24)" }],
      },
    });
  }

  function initStream(root, data) {
    render(root, "#chart-stream", {
      ...baseChart("area", 320),
      chart: { ...baseChart("area", 320).chart, stacked: true },
      series: data.quadrant_stream.series.map(item => ({ name: item.label, data: item.data })),
      colors: data.quadrant_stream.series.map(item => item.accent),
      labels: data.timeseries.labels,
      yaxis: { min: 0, labels: { formatter: v => Math.round(v) } },
      fill: { opacity: 0.54 },
    });
  }

  function initHeatmap(root, data) {
    const levels = { empty: 0, low: 2, mid: 5, high: 8, peak: 10 };
    const colors = {
      empty: "rgba(245,241,234,0.06)",
      low: "#6FB7D8",
      mid: "#CF9D7B",
      high: "#F4A261",
      peak: "#FF6B5F",
    };
    const weeks = [];
    data.heatmap.forEach((day, idx) => {
      const week = Math.floor(idx / 7);
      if (!weeks[week]) weeks[week] = { name: `W${week + 1}`, data: [] };
      weeks[week].data.push({
        x: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][day.weekday],
        y: levels[day.level] || 0,
        fillColor: colors[day.level] || colors.empty,
        meta: day,
      });
    });
    render(root, "#chart-heatmap", {
      ...baseChart("heatmap", data.window_days >= 365 ? 520 : 300),
      series: weeks,
      plotOptions: { heatmap: { shadeIntensity: 0, colorScale: { ranges: [] } } },
      tooltip: {
        theme: "dark",
        custom: ({ seriesIndex, dataPointIndex, w }) => {
          const meta = w.config.series[seriesIndex].data[dataPointIndex].meta;
          return `<div class="saga-chart-tip">${meta.date}<br>${meta.count} entries · avg ${meta.average}</div>`;
        },
      },
    });
  }

  function initBuckets(root, data) {
    const p = palette();
    const bucket = data.challenge_bucket_series || {};
    render(root, "#chart-buckets", {
      ...baseChart("line", 320),
      series: [
        { name: "Anchor", data: bucket.anchor || [] },
        { name: "Improver", data: bucket.improver || [] },
        { name: "Enricher", data: bucket.enricher || [] },
        { name: "Composite", data: bucket.composite || [] },
      ],
      colors: ["#61D394", "#7C9CFF", "#F6D365", p.champagne],
      labels: data.timeseries.labels,
      yaxis: { min: 0, max: 100 },
    });
  }

  function initScatter(root, data) {
    const byType = {};
    data.scatter.forEach(point => {
      byType[point.archetype] = byType[point.archetype] || { color: point.accent, data: [] };
      byType[point.archetype].data.push({ x: point.mood_load, y: point.output_index, meta: point });
    });
    render(root, "#chart-scatter", {
      ...baseChart("scatter", 340),
      series: Object.entries(byType).map(([name, item]) => ({ name, data: item.data })),
      colors: Object.values(byType).map(item => item.color),
      xaxis: { min: 0, max: 100, title: { text: "Mood load" } },
      yaxis: { min: 0, max: 100, title: { text: "Output index" } },
      markers: { size: 6, strokeWidth: 2 },
      annotations: {
        xaxis: [{ x: 65, borderColor: "rgba(245,241,234,0.2)" }],
        yaxis: [{ y: 55, borderColor: "rgba(245,241,234,0.2)" }],
      },
      tooltip: {
        theme: "dark",
        custom: ({ seriesIndex, dataPointIndex, w }) => {
          const meta = w.config.series[seriesIndex].data[dataPointIndex].meta;
          return `<div class="saga-chart-tip">${meta.label}<br>${meta.archetype}<br>Mood ${meta.mood_load} · Output ${meta.output_index}</div>`;
        },
      },
    });
  }

  function initDonut(root, selector, labels, values, colors) {
    const p = palette();
    render(root, selector, {
      ...baseChart("donut", 300),
      series: values,
      labels,
      colors,
      plotOptions: { pie: { donut: { size: "68%", labels: { show: true, total: { show: true, color: p.text } } } } },
      stroke: { width: 1, colors: ["rgba(12,21,25,0.88)"] },
    });
  }

  function initArchetypes(root, data) {
    initDonut(
      root,
      "#chart-archetypes",
      data.archetype_distribution.map(item => item.archetype),
      data.archetype_distribution.map(item => item.count),
      ["#CF9D7B", "#E27F6F", "#61D394", "#7C9CFF", "#F6D365", "#D58BFF", "#6FB7D8", "#F4A261", "#9DBA5A"]
    );
  }

  function initDow(root, data) {
    render(root, "#chart-dow", {
      ...baseChart("radar", 320),
      series: [
        { name: "Mood load", data: data.dow_profile.map(item => item.mood_load_avg) },
        { name: "Output", data: data.dow_profile.map(item => item.output_avg) },
      ],
      labels: data.dow_profile.map(item => item.weekday),
      colors: ["#E27F6F", "#EACEAA"],
      yaxis: { min: 0, max: 100 },
    });
  }

  function initBlock(root, data) {
    const block = data.block_mood;
    const series = block.blocks.map(name => ({
      name,
      data: block.quadrants.map(quadrant => ({ x: quadrant[0].toUpperCase() + quadrant.slice(1), y: block.matrix[name][quadrant] || 0 })),
    }));
    render(root, "#chart-block", {
      ...baseChart("heatmap", 320),
      series,
      colors: [palette().brass],
      plotOptions: { heatmap: { shadeIntensity: 0.42 } },
    });
  }

  function initFamilyDonut(root, data) {
    initDonut(
      root,
      "#chart-family-donut",
      data.distribution.map(item => item.label),
      data.distribution.map(item => item.count),
      data.distribution.map(item => item.accent)
    );
  }

  function init(explicitWindow) {
    const roots = Array.from(document.querySelectorAll("[data-saga-dashboard]"));
    roots.forEach(root => {
      const data = payloadFor(root, explicitWindow);
      if (!data) return;
      initKpis(root, data);
      initComove(root, data);
      initAffect(root, data);
      initStream(root, data);
      initHeatmap(root, data);
      initBuckets(root, data);
      initScatter(root, data);
      initArchetypes(root, data);
      initDow(root, data);
      initBlock(root, data);
      initFamilyDonut(root, data);
    });
  }

  document.addEventListener("DOMContentLoaded", () => init());
  document.body.addEventListener("htmx:afterSwap", event => {
    if (event.detail && event.detail.target && event.detail.target.querySelector("[data-saga-dashboard]")) {
      init();
    }
  });

  window.SagaDashboard = { init };
})();
