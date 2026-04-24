/* War Room — Chart.js initialisation
 * Called after HTMX loads the trophies panel (htmx:afterSettle on #trophy-slot).
 * Also called on DOMContentLoaded in case the panel is present on first paint.
 */

(function () {
  'use strict';

  // Global Chart.js defaults — match design tokens
  function applyGlobalDefaults() {
    if (!window.Chart) return;
    Chart.defaults.font.family = "'Manrope', system-ui, sans-serif";
    Chart.defaults.font.size   = 12;
    Chart.defaults.color       = '#74796c';
    Chart.defaults.plugins.legend.display = false;
    Chart.defaults.plugins.legend.labels.boxWidth = 16;
    Chart.defaults.plugins.legend.labels.boxHeight = 8;
    Chart.defaults.plugins.legend.labels.padding = 10;
    Chart.defaults.plugins.tooltip.backgroundColor = 'rgba(28,28,24,0.88)';
    Chart.defaults.plugins.tooltip.titleColor       = '#F3EDE3';
    Chart.defaults.plugins.tooltip.bodyColor        = '#c2c8c0';
    Chart.defaults.plugins.tooltip.padding          = 10;
    Chart.defaults.plugins.tooltip.cornerRadius     = 6;
    Chart.defaults.plugins.tooltip.displayColors    = true;
    Chart.defaults.plugins.tooltip.boxWidth         = 8;
    Chart.defaults.plugins.tooltip.boxHeight        = 8;
  }

  // Inject Chart.js animation config (functions can't be JSON-serialised server-side)
  function applyAnimation(config) {
    config.options = config.options || {};
    var type = config.type;

    // Base animation — all chart types
    config.options.animation = Object.assign(config.options.animation || {}, {
      duration: 700,
      easing: 'easeOutQuart',
    });

    if (type === 'bar') {
      // Stagger bars left-to-right; datasets animate together per index
      config.options.animation.delay = function (ctx) {
        return ctx.type === 'data' ? ctx.dataIndex * 55 : 0;
      };
    }

    if (type === 'line') {
      // Stagger points along the line
      config.options.animation.delay = function (ctx) {
        return ctx.type === 'data' ? ctx.dataIndex * 35 : 0;
      };
    }

    if (type === 'doughnut') {
      config.options.animation.animateRotate = true;
      config.options.animation.animateScale  = false;
    }

    return config;
  }

  function applyLegendPolish(config, canvas) {
    if (!config.options || !config.options.plugins || !config.options.plugins.legend) return config;

    if (canvas.id === 'chart-priority-burn-rate') {
      config.options.plugins.legend.labels = Object.assign(
        config.options.plugins.legend.labels || {},
        {
          boxWidth: 18,
          boxHeight: 8,
          generateLabels: function (chart) {
            const base = Chart.defaults.plugins.legend.labels.generateLabels(chart);
            return base
              .filter(function (item) {
                return item.datasetIndex % 2 === 1;
              })
              .map(function (item) {
                return Object.assign({}, item, {
                  text: item.text.replace(' completed', ''),
                });
              });
          },
        }
      );
      config.options.plugins.legend.onClick = null;
    }

    return config;
  }

  function initWarRoomCharts() {
    if (!window.Chart) return;
    applyGlobalDefaults();

    const canvases = document.querySelectorAll('[data-chart]');
    canvases.forEach(function (canvas) {
      // Destroy existing instance to avoid duplicate chart error on re-render
      const existing = Chart.getChart(canvas);
      if (existing) existing.destroy();

      let config;
      try {
        config = JSON.parse(canvas.getAttribute('data-chart'));
      } catch (e) {
        console.warn('War Room: failed to parse chart config', e);
        return;
      }

      // Strip private underscore keys before passing to Chart.js
      delete config._center;

      applyAnimation(config);
      applyLegendPolish(config, canvas);
      new Chart(canvas, config);
    });
  }

  // Init on first paint (e.g. if panel already in DOM)
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initWarRoomCharts);
  } else {
    initWarRoomCharts();
  }

  // Re-init after every HTMX settle (covers tab switches + refreshes)
  document.addEventListener('htmx:afterSettle', function (evt) {
    // Only re-run when the trophies panel was swapped
    if (evt.detail && evt.detail.target && evt.detail.target.id === 'trophy-slot') {
      initWarRoomCharts();
    }
  });

  // Expose for manual calls if needed
  window.initWarRoomCharts = initWarRoomCharts;
}());
