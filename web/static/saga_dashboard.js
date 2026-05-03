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

  function flameHeatmapRanges(max = 100) {
    const scale = max <= 10
      ? [
        { from: 0, to: 0, color: "#364348", name: "no load" },
        { from: 1, to: 2, color: "#4A1F1C", name: "light" },
        { from: 3, to: 5, color: "#A83A22", name: "warm" },
        { from: 6, to: 8, color: "#F97316", name: "hot" },
        { from: 9, to: 10, color: "#FFE08A", name: "intense" },
      ]
      : [
        { from: 0, to: 0, color: "#364348", name: "no load" },
        { from: 1, to: 24, color: "#4A1F1C", name: "light" },
        { from: 25, to: 49, color: "#A83A22", name: "warm" },
        { from: 50, to: 74, color: "#F97316", name: "hot" },
        { from: 75, to: 100, color: "#FFE08A", name: "intense" },
      ];
    return scale;
  }

  function systemMatrixRanges() {
    return [
      { from: -1, to: -1, color: "#364348", name: "No data" },
      { from: 0, to: 24, color: "#8A2C25", name: "Strained" },
      { from: 25, to: 49, color: "#D05A2D", name: "Weak" },
      { from: 50, to: 74, color: "#F2B84B", name: "Holding" },
      { from: 75, to: 100, color: "#61D394", name: "Strong" },
    ];
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
    const points = (data.timeseries.labels || []).map((label, idx) => ({
      x: data.timeseries.avg_pleasantness[idx],
      y: data.timeseries.avg_energy[idx],
      meta: { label, date: data.timeseries.dates[idx] },
    })).filter(point => point.x !== null && point.y !== null);
    render(root, "#chart-affect", {
      ...baseChart("scatter", 340),
      series: [{ name: "Mood center", data: points }],
      colors: ["#F4C430"],
      xaxis: { min: -7, max: 7, tickAmount: 14, title: { text: "Pleasantness" } },
      yaxis: { min: -7, max: 7, tickAmount: 14, title: { text: "Energy" } },
      markers: { size: 7, strokeWidth: 2 },
      annotations: {
        xaxis: [{ x: 0, borderColor: "rgba(245,241,234,0.24)" }],
        yaxis: [{ y: 0, borderColor: "rgba(245,241,234,0.24)" }],
      },
      tooltip: {
        theme: "dark",
        custom: ({ seriesIndex, dataPointIndex, w }) => {
          const point = w.config.series[seriesIndex].data[dataPointIndex];
          return `<div class="saga-chart-tip">${point.meta.label}<br>P ${point.x} · E ${point.y}</div>`;
        },
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
    const weeks = [];
    data.heatmap.forEach((day, idx) => {
      const week = Math.floor(idx / 7);
      if (!weeks[week]) weeks[week] = { name: `W${week + 1}`, data: [] };
      weeks[week].data.push({
        x: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][day.weekday],
        y: levels[day.level] || 0,
        meta: day,
      });
    });
    render(root, "#chart-heatmap", {
      ...baseChart("heatmap", data.window_days >= 365 ? 520 : 300),
      series: weeks,
      plotOptions: {
        heatmap: {
          shadeIntensity: 0,
          colorScale: { ranges: flameHeatmapRanges(10) },
        },
      },
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
    render(root, "#chart-archetypes", {
      ...baseChart("bar", 320),
      series: [{ name: "Days", data: data.archetype_distribution.map(item => item.count) }],
      colors: ["#CF9D7B"],
      plotOptions: { bar: { horizontal: true, borderRadius: 3, distributed: true } },
      xaxis: {
        categories: data.archetype_distribution.map(item => item.archetype),
        labels: { formatter: v => Math.round(v) },
      },
      yaxis: { labels: { maxWidth: 160 } },
    });
  }

  function initDow(root, data) {
    render(root, "#chart-dow", {
      ...baseChart("bar", 320),
      series: [
        { name: "Mood load", data: data.dow_profile.map(item => item.mood_load_avg) },
        { name: "Output", data: data.dow_profile.map(item => item.output_avg) },
      ],
      colors: ["#E27F6F", "#EACEAA"],
      plotOptions: { bar: { columnWidth: "48%", borderRadius: 3 } },
      xaxis: { categories: data.dow_profile.map(item => item.weekday) },
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

  function initSystemsMatrix(root, data) {
    if (!data.grimoire || !data.grimoire.charts) return;
    const matrix = data.grimoire.charts.systems_matrix || {};
    const labels = data.grimoire.charts.labels || [];
    const dates = data.grimoire.charts.dates || [];
    const series = Object.entries(matrix).map(([name, values]) => ({
      name,
      data: values.map((value, idx) => ({ x: labels[idx], y: value, meta: { date: dates[idx], system: name } })),
    }));
    render(root, "#chart-systems-matrix", {
      ...baseChart("heatmap", 340),
      series,
      plotOptions: {
        heatmap: {
          shadeIntensity: 0,
          colorScale: { ranges: systemMatrixRanges() },
        },
      },
      dataLabels: {
        enabled: true,
        formatter: value => value < 0 ? "—" : Math.round(value),
        style: { colors: ["#0C1519"] },
      },
      tooltip: {
        theme: "dark",
        custom: ({ seriesIndex, dataPointIndex, w }) => {
          const point = w.config.series[seriesIndex].data[dataPointIndex];
          const value = point.y < 0 ? "No data" : `${Math.round(point.y)} / 100`;
          return `<div class="saga-chart-tip">${point.meta.system} · ${point.meta.date || point.x}<br>${value}</div>`;
        },
      },
    });
  }

  function initTimelineHeartbeat(root, data) {
    if (!data.grimoire || !data.grimoire.charts) return;
    const heartbeat = data.grimoire.charts.timeline_heartbeat || {};
    render(root, "#chart-timeline-heartbeat", {
      ...baseChart("line", 360),
      series: heartbeat.series || [],
      colors: ["#7C9CFF", "#EACEAA", "#F6D365", "#61D394"],
      labels: heartbeat.labels || [],
      yaxis: { min: 0, max: 100, title: { text: "Score" } },
      stroke: { curve: "smooth", width: 3 },
      markers: { size: 3, strokeWidth: 0 },
      tooltip: {
        theme: "dark",
        shared: true,
        intersect: false,
        y: {
          formatter: value => value === null || value === undefined ? "No signal" : `${Math.round(value)} / 100`,
        },
      },
    });
  }

  function relationshipCopy(relationship) {
    const copy = {
      mood_daily: "Each dot is one day with Saga mood and Daily Execution data. X is mood pleasantness from -7 to +7; Y is Quest/Pomo execution from 0 to 100.",
      mood_long: "Each dot is one day with Saga mood and Hard 90 data. X is mood pleasantness from -7 to +7; Y is long-game integrity from 0 to 100.",
      curiosity_long: "Each dot is one day with Tiny Experiment and Hard 90 data. X is Curiosity/Evolution from 0 to 100; Y is long-game integrity from 0 to 100.",
      holiday_mood: "Each dot is one day with Saga mood data. X is Holiday Load, where holiday days sit at 100; Y is mood load from 0 to 100.",
      holiday_daily: "Each dot is one day with Daily Execution data. X is Holiday Load, where holiday days sit at 100; Y is Quest/Pomo execution from 0 to 100.",
      holiday_focus: "Each dot is one day with focus data. X is Holiday Load, where holiday days sit at 100; Y is focus quality from 0 to 100.",
    };
    return copy[relationship.key] || "Each dot is one day. The chart tests whether the selected signals move together.";
  }

  function drawRelationship(root, relationship) {
    const points = (relationship.points || []).map(point => ({ x: point.x, y: point.y, meta: point }));
    render(root, "#chart-relationship-truth", {
      ...baseChart("scatter", 340),
      series: [{ name: relationship.label, data: points }],
      colors: ["#F6D365"],
      xaxis: {
        min: relationship.x_min,
        max: relationship.x_max,
        title: { text: relationship.x_label },
      },
      yaxis: {
        min: relationship.y_min,
        max: relationship.y_max,
        title: { text: relationship.y_label },
      },
      annotations: {
        xaxis: relationship.x_min < 0 ? [{ x: 0, borderColor: "rgba(245,241,234,0.22)" }] : [],
        yaxis: [{ y: 70, borderColor: "rgba(245,241,234,0.18)" }],
      },
      markers: { size: 7, strokeWidth: 1 },
      tooltip: {
        theme: "dark",
        custom: ({ seriesIndex, dataPointIndex, w }) => {
          const point = w.config.series[seriesIndex].data[dataPointIndex];
          return `<div class="saga-chart-tip">${point.meta.label}<br>${relationship.x_label}: ${point.x}<br>${relationship.y_label}: ${point.y}</div>`;
        },
      },
    });
  }

  function initRelationshipTruthDetector(root, data) {
    if (!data.grimoire || !data.grimoire.charts) return;
    const relationships = data.grimoire.charts.relationships || [];
    if (!relationships.length) return;
    const byKey = Object.fromEntries(relationships.map(item => [item.key, item]));
    const buttons = Array.from(root.querySelectorAll("[data-relationship]"));
    const copy = root.querySelector("[data-relationship-copy]");
    function activate(key) {
      const relationship = byKey[key] || relationships[0];
      buttons.forEach(button => button.classList.toggle("is-active", button.dataset.relationship === relationship.key));
      if (copy) copy.textContent = relationshipCopy(relationship);
      drawRelationship(root, relationship);
    }
    buttons.forEach(button => {
      button.onclick = () => activate(button.dataset.relationship);
    });
    const active = buttons.find(button => button.classList.contains("is-active"));
    activate(active ? active.dataset.relationship : relationships[0].key);
  }

  function correlationRanges() {
    return [
      { from: -1, to: -0.5, color: "#E27F6F", name: "Negative" },
      { from: -0.49, to: 0.49, color: "#364348", name: "Weak/none" },
      { from: 0.5, to: 0.79, color: "#F6D365", name: "Positive" },
      { from: 0.8, to: 1, color: "#61D394", name: "Strong" },
    ];
  }

  function initCorrelationMap(root, data) {
    if (!data.grimoire || !data.grimoire.charts) return;
    const matrix = data.grimoire.charts.correlation_matrix || {};
    const series = (matrix.series || []).map(row => ({
      name: row.name,
      data: (row.data || []).map(cell => ({ x: cell.x, y: cell.y, meta: cell })),
    }));
    render(root, "#chart-correlation-map", {
      ...baseChart("heatmap", 340),
      series,
      plotOptions: {
        heatmap: {
          shadeIntensity: 0,
          colorScale: { ranges: correlationRanges() },
        },
      },
      dataLabels: {
        enabled: true,
        formatter: value => value === null || value === undefined ? "—" : Number(value).toFixed(2),
        style: { colors: ["#F5F1EA"] },
      },
      tooltip: {
        theme: "dark",
        custom: ({ seriesIndex, dataPointIndex, w }) => {
          const cell = w.config.series[seriesIndex].data[dataPointIndex].meta;
          const value = cell.y === null || cell.y === undefined ? "Insufficient data" : cell.y.toFixed(2);
          return `<div class="saga-chart-tip">${cell.metric_y} ↔ ${cell.metric_x}<br>${value}<br>${cell.paired_days} paired day${cell.paired_days === 1 ? "" : "s"}</div>`;
        },
      },
    });
  }

  function initExecLong(root, data) {
    if (!data.grimoire || !data.grimoire.charts) return;
    const grouped = { "Pleasant mood": [], "Unpleasant mood": [], "No mood captured": [] };
    (data.grimoire.charts.execution_long_game || []).forEach(point => {
      const key = point.mood || "No mood captured";
      grouped[key].push({ x: point.x, y: point.y, meta: point });
    });
    render(root, "#chart-exec-long", {
      ...baseChart("scatter", 340),
      series: Object.entries(grouped)
        .filter(([, points]) => points.length)
        .map(([name, points]) => ({ name, data: points })),
      colors: ["#61D394", "#E27F6F", "#8FA1A8"],
      xaxis: { min: 0, max: 100, title: { text: "Daily execution" } },
      yaxis: { min: 0, max: 100, title: { text: "Long game integrity" } },
      annotations: {
        xaxis: [{ x: 60, borderColor: "rgba(245,241,234,0.24)", label: { text: "execution line", style: { color: "#0C1519", background: "#EACEAA" } } }],
        yaxis: [{ y: 70, borderColor: "rgba(245,241,234,0.24)", label: { text: "integrity line", style: { color: "#0C1519", background: "#EACEAA" } } }],
      },
      markers: { size: 7, strokeWidth: 1 },
      tooltip: {
        theme: "dark",
        custom: ({ seriesIndex, dataPointIndex, w }) => {
          const meta = w.config.series[seriesIndex].data[dataPointIndex].meta;
          const experiment = meta.experiment ? "<br>Experiment active/touched" : "";
          return `<div class="saga-chart-tip">${meta.label}<br>Execution ${meta.x} · Long game ${meta.y}<br>Pleasantness ${meta.pleasantness}${experiment}</div>`;
        },
      },
    });
  }

  function initMoodSplit(root, data) {
    if (!data.grimoire || !data.grimoire.charts) return;
    const rows = data.grimoire.charts.mood_correlation || [];
    const output = rows
      .filter(row => row.output !== null && row.output !== undefined)
      .map(row => ({ x: row.pleasantness, y: row.output, meta: row }));
    const integrity = rows
      .filter(row => row.integrity !== null && row.integrity !== undefined)
      .map(row => ({ x: row.pleasantness, y: row.integrity, meta: row }));
    render(root, "#chart-mood-split", {
      ...baseChart("scatter", 300),
      series: [
        { name: "Daily output", data: output },
        { name: "Hard 90 integrity", data: integrity },
      ],
      colors: ["#F6D365", "#61D394"],
      xaxis: { min: -7, max: 7, tickAmount: 14, title: { text: "Mood pleasantness" } },
      yaxis: { min: 0, max: 100, title: { text: "Score" } },
      annotations: {
        xaxis: [{ x: 0, borderColor: "rgba(245,241,234,0.24)", label: { text: "neutral mood", style: { color: "#0C1519", background: "#EACEAA" } } }],
      },
      markers: { size: 7, strokeWidth: 1 },
      tooltip: {
        theme: "dark",
        custom: ({ seriesIndex, dataPointIndex, w }) => {
          const point = w.config.series[seriesIndex].data[dataPointIndex];
          const metric = w.config.series[seriesIndex].name;
          return `<div class="saga-chart-tip">${point.meta.label}<br>${metric}: ${point.y}<br>Pleasantness ${point.x} · mood load ${point.meta.mood_load}</div>`;
        },
      },
    });
  }

  function initFocusQuality(root, data) {
    if (!data.grimoire || !data.grimoire.charts) return;
    const rows = data.grimoire.charts.focus_quality || [];
    render(root, "#chart-focus-quality", {
      ...baseChart("bar", 320),
      series: [
        { name: "Pomos", data: rows.map(row => row.pomos) },
        { name: "Interruptions", data: rows.map(row => row.interruptions) },
        { name: "Hollow", data: rows.map(row => row.hollow) },
        { name: "Berserker", data: rows.map(row => row.berserker) },
      ],
      colors: ["#EACEAA", "#E27F6F", "#6FB7D8", "#F6D365"],
      xaxis: { categories: rows.map(row => row.label) },
      plotOptions: { bar: { borderRadius: 3 } },
    });
  }

  function initExperimentRunway(root, data) {
    if (!data.grimoire || !data.grimoire.charts) return;
    const rows = data.grimoire.charts.experiment_runway || [];
    render(root, "#chart-experiment-runway", {
      ...baseChart("bar", 320),
      series: [
        { name: "Active", data: rows.map(row => row.active) },
        { name: "Touched", data: rows.map(row => row.touched) },
        { name: "Verdict due", data: rows.map(row => row.verdict_due) },
      ],
      colors: ["#7C9CFF", "#61D394", "#E27F6F"],
      xaxis: { categories: rows.map(row => row.label) },
      plotOptions: { bar: { borderRadius: 3 } },
    });
  }

  function initBucketRisk(root, data) {
    if (!data.grimoire || !data.grimoire.charts) return;
    const rows = data.grimoire.charts.bucket_risk || [];
    render(root, "#chart-bucket-risk", {
      ...baseChart("bar", 300),
      series: [
        { name: "Misses on pleasant days", data: rows.map(row => row.pleasant) },
        { name: "Misses on unpleasant days", data: rows.map(row => row.unpleasant) },
      ],
      colors: ["#61D394", "#E27F6F"],
      xaxis: { categories: rows.map(row => row.bucket) },
      yaxis: {
        min: 0,
        title: { text: "Missed Hard 90 entries" },
        labels: { formatter: value => Math.round(value) },
      },
      plotOptions: { bar: { columnWidth: "48%", borderRadius: 3 } },
      tooltip: {
        theme: "dark",
        y: {
          formatter: value => `${Math.round(value)} missed/partial task ${Math.round(value) === 1 ? "entry" : "entries"}`,
        },
      },
    });
  }

  function initDowSystem(root, data) {
    if (!data.grimoire || !data.grimoire.charts) return;
    const rows = data.grimoire.charts.dow_system || [];
    render(root, "#chart-dow-system", {
      ...baseChart("bar", 320),
      series: [
        { name: "Daily", data: rows.map(row => row.daily) },
        { name: "Long Game", data: rows.map(row => row.long_game) },
        { name: "Emotion", data: rows.map(row => row.emotion) },
      ],
      colors: ["#EACEAA", "#61D394", "#7C9CFF"],
      xaxis: { categories: rows.map(row => row.weekday) },
      yaxis: { min: 0, max: 100 },
      plotOptions: { bar: { borderRadius: 3, columnWidth: "54%" } },
    });
  }

  function init(explicitWindow) {
    const roots = Array.from(document.querySelectorAll("[data-saga-dashboard]"));
    roots.forEach(root => {
      const data = payloadFor(root, explicitWindow);
      if (!data) return;
      initKpis(root, data);
      initTimelineHeartbeat(root, data);
      initRelationshipTruthDetector(root, data);
      initCorrelationMap(root, data);
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
