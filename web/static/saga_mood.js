(function () {
  function findCell(catalog, energy, pleasantness) {
    return catalog.find(cell => cell.energy === energy && cell.pleasantness === pleasantness) || null;
  }

  function axisMeta(catalog) {
    const energies = [...new Set(catalog.map(cell => Number(cell.energy)))].sort((a, b) => b - a);
    const pleasantness = [...new Set(catalog.map(cell => Number(cell.pleasantness)))].sort((a, b) => a - b);
    return {
      maxEnergy: Math.max(...energies),
      minEnergy: Math.min(...energies),
      minPleasantness: Math.min(...pleasantness),
      maxPleasantness: Math.max(...pleasantness),
      columns: pleasantness.length || 1,
    };
  }

  function dispatchMoodFx(type, cell) {
    window.dispatchEvent(new CustomEvent("saga:mood-fx", { detail: { type, cell } }));
  }

  window.sagaMoodCapture = function sagaMoodCapture(catalog) {
    const meta = axisMeta(catalog);
    return {
      catalog,
      axis: meta,
      selected: null,
      hovered: null,
      note: "",
      confirmation: "",
      draftPaused: false,
      init() {
        const saved = localStorage.getItem("saga.mood.draft.v1");
        if (saved) {
          try {
            const draft = JSON.parse(saved);
            const restored = findCell(this.catalog, Number(draft.energy), Number(draft.pleasantness));
            if (restored) this.selected = restored;
            this.note = draft.note || "";
          } catch (_) {}
        }
        this.$watch("selected", () => this.saveDraft());
        this.$watch("note", () => this.saveDraft());
      },
      saveDraft() {
        if (this.draftPaused) return;
        localStorage.setItem("saga.mood.draft.v1", JSON.stringify({
          energy: this.selected ? this.selected.energy : null,
          pleasantness: this.selected ? this.selected.pleasantness : null,
          note: this.note,
        }));
      },
      canSubmit() {
        return Boolean(this.selected);
      },
      previewCell() {
        return this.hovered || this.selected;
      },
      quadrantLabel(quadrant) {
        return {
          yellow: "High energy pleasant",
          red: "High energy unpleasant",
          green: "Low energy pleasant",
          blue: "Low energy unpleasant",
        }[quadrant] || quadrant;
      },
      coordsLabel(cell) {
        return `Energy ${cell.energy}, pleasantness ${cell.pleasantness}`;
      },
      axisEnergy() {
        const cell = this.previewCell();
        if (!cell) return 50;
        return ((this.axis.maxEnergy - cell.energy) / (this.axis.maxEnergy - this.axis.minEnergy)) * 100;
      },
      axisPleasantness() {
        const cell = this.previewCell();
        if (!cell) return 50;
        return ((cell.pleasantness - this.axis.minPleasantness) / (this.axis.maxPleasantness - this.axis.minPleasantness)) * 100;
      },
      hoverCell(energy, pleasantness) {
        const cell = findCell(this.catalog, energy, pleasantness);
        if (!cell) return;
        this.hovered = cell;
        dispatchMoodFx("hover", cell);
      },
      clearHover() {
        this.hovered = null;
      },
      toggleCell(energy, pleasantness) {
        const cell = findCell(this.catalog, energy, pleasantness);
        if (!cell) return;
        if (this.selected && this.selected.energy === energy && this.selected.pleasantness === pleasantness) {
          this.selected = null;
          dispatchMoodFx("clear", cell);
          return;
        }
        this.selected = cell;
        dispatchMoodFx("select", cell);
      },
      moveFocus(event, index) {
        const keyMoves = {
          ArrowRight: 1,
          ArrowLeft: -1,
          ArrowDown: this.axis.columns,
          ArrowUp: -this.axis.columns,
        };
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          const cell = this.catalog[index];
          this.toggleCell(cell.energy, cell.pleasantness);
          return;
        }
        if (!(event.key in keyMoves)) return;
        event.preventDefault();
        const next = Math.max(0, Math.min(this.catalog.length - 1, index + keyMoves[event.key]));
        const buttons = event.currentTarget.closest(".saga-mood-grid").querySelectorAll(".saga-mood-cell");
        if (buttons[next]) buttons[next].focus();
      },
      finishCapture() {
        this.draftPaused = true;
        this.selected = null;
        this.hovered = null;
        this.note = "";
        this.confirmation = "Entry saved.";
        localStorage.removeItem("saga.mood.draft.v1");
        dispatchMoodFx("clear", null);
        this.$nextTick(() => {
          this.draftPaused = false;
          if (this.$refs.noteInput) this.$refs.noteInput.focus();
        });
        setTimeout(() => this.confirmation = "", 1800);
      },
    };
  };

  function initMoodCanvas() {
    const canvas = document.getElementById("saga-mood-fx");
    const grid = document.querySelector(".saga-mood-grid");
    if (!canvas || !grid) return;
    const ctx = canvas.getContext("2d");
    const ripples = [];

    function resize() {
      const rect = canvas.getBoundingClientRect();
      const scale = window.devicePixelRatio || 1;
      canvas.width = Math.max(1, Math.round(rect.width * scale));
      canvas.height = Math.max(1, Math.round(rect.height * scale));
      ctx.setTransform(scale, 0, 0, scale, 0, 0);
      draw();
    }

    function cellCenter(cell) {
      if (!cell) return null;
      const selector = `.saga-mood-cell[data-energy="${cell.energy}"][data-pleasantness="${cell.pleasantness}"]`;
      const el = grid.querySelector(selector);
      if (!el) return null;
      const gridRect = grid.getBoundingClientRect();
      const rect = el.getBoundingClientRect();
      return {
        x: rect.left - gridRect.left + rect.width / 2,
        y: rect.top - gridRect.top + rect.height / 2,
        radius: Math.max(rect.width, rect.height) / 2,
        accent: cell.accent,
        energy: Number(cell.energy),
        pleasantness: Number(cell.pleasantness),
      };
    }

    function draw() {
      const rect = canvas.getBoundingClientRect();
      ctx.clearRect(0, 0, rect.width, rect.height);
      ripples.forEach(ripple => {
        ctx.beginPath();
        ctx.arc(ripple.x, ripple.y, ripple.radius, 0, Math.PI * 2);
        ctx.strokeStyle = ripple.color;
        ctx.globalAlpha = ripple.alpha;
        ctx.lineWidth = ripple.width;
        ctx.stroke();
      });
      ctx.globalAlpha = 1;
    }

    function animateRipple(origin, strong) {
      if (!origin) return;
      const highEnergy = Math.max(0, origin.energy) / 7;
      const lowEnergy = Math.max(0, -origin.energy) / 7;
      const unpleasant = Math.max(0, -origin.pleasantness) / 7;
      const pleasant = Math.max(0, origin.pleasantness) / 7;
      const ripple = {
        x: origin.x,
        y: origin.y,
        radius: origin.radius,
        alpha: strong ? 0.72 + highEnergy * 0.18 : 0.28 + highEnergy * 0.2,
        width: strong ? 2.2 + unpleasant * 1.4 : 1.1 + unpleasant * 0.9,
        color: origin.accent,
      };
      ripples.push(ripple);
      const timeline = window.anime ? window.anime : ({ targets, radius, alpha, duration, update, complete }) => {
        Object.assign(targets, { radius, alpha });
        if (update) update();
        window.setTimeout(() => complete && complete(), duration || 0);
      };
      timeline({
        targets: ripple,
        radius: origin.radius + (strong ? 110 + lowEnergy * 90 + pleasant * 45 : 52 + lowEnergy * 52 + pleasant * 22),
        alpha: 0,
        width: 0.5,
        easing: unpleasant > pleasant ? "easeOutExpo" : "easeOutQuart",
        duration: strong ? 840 - highEnergy * 220 + lowEnergy * 140 : 500 - highEnergy * 120 + lowEnergy * 120,
        update: draw,
        complete: () => {
          const idx = ripples.indexOf(ripple);
          if (idx >= 0) ripples.splice(idx, 1);
          draw();
        },
      });
    }

    window.addEventListener("resize", resize);
    window.addEventListener("saga:mood-fx", event => {
      if (!event.detail || event.detail.type === "clear") {
        ripples.length = 0;
        draw();
        return;
      }
      animateRipple(cellCenter(event.detail.cell), event.detail.type === "select");
    });
    resize();
  }

  document.addEventListener("DOMContentLoaded", initMoodCanvas);
  document.body.addEventListener("htmx:afterSwap", initMoodCanvas);
})();
