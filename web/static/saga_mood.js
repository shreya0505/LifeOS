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

  window.sagaMoodCapture = function sagaMoodCapture(catalog) {
    return {
      catalog,
      axis: axisMeta(catalog),
      stage: "quadrants",
      activeQuadrant: null,
      selected: null,
      hovered: null,
      hoveredQuadrant: null,
      note: "",
      confirmation: "",
      draftPaused: false,
      quadrants: [
        { key: "red", name: "Hellfire", label: "High energy unpleasant", accent: "#8F1F17" },
        { key: "yellow", name: "Radiance", label: "High energy pleasant", accent: "#F4C430" },
        { key: "blue", name: "Abyss", label: "Low energy unpleasant", accent: "#252A33" },
        { key: "green", name: "Sanctuary", label: "Low energy pleasant", accent: "#2F7D4A" },
      ],
      init() {
        const saved = localStorage.getItem("saga.mood.draft.v1");
        if (saved) {
          try {
            const draft = JSON.parse(saved);
            const restored = findCell(this.catalog, Number(draft.energy), Number(draft.pleasantness));
            if (restored) {
              this.selected = restored;
              this.activeQuadrant = restored.quadrant;
              this.stage = "moods";
            }
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
      quadrantInfo(quadrant) {
        return this.quadrants.find(item => item.key === quadrant) || null;
      },
      previewCell() {
        return this.hovered || this.selected;
      },
      previewItem() {
        if (this.hovered) return this.hovered;
        if (this.hoveredQuadrant) return { ...this.hoveredQuadrant, quadrant: this.hoveredQuadrant.key, isQuadrant: true };
        if (this.selected) return this.selected;
        if (this.stage === "moods" && this.activeQuadrant) {
          const quadrant = this.quadrantInfo(this.activeQuadrant);
          return quadrant ? { ...quadrant, quadrant: quadrant.key, isQuadrant: true } : null;
        }
        return null;
      },
      previewAccent() {
        const item = this.previewItem();
        return item ? item.accent : "#CF9D7B";
      },
      previewLabel() {
        const item = this.previewItem();
        if (!item) return "Choose a realm";
        return item.isQuadrant ? item.label : this.quadrantLabel(item.quadrant);
      },
      previewTitle() {
        const item = this.previewItem();
        if (!item) return "Name it";
        return item.isQuadrant ? item.name : item.word;
      },
      previewDetail() {
        const item = this.previewItem();
        if (!item) return "Start broad, then choose the exact word.";
        return item.isQuadrant ? item.label : this.coordsLabel(item);
      },
      quadrantLabel(quadrant) {
        return {
          yellow: "Radiance",
          red: "Hellfire",
          green: "Sanctuary",
          blue: "Abyss",
        }[quadrant] || quadrant;
      },
      coordsLabel(cell) {
        return `Energy ${cell.energy}, pleasantness ${cell.pleasantness}`;
      },
      energyAxisLabel() {
        return this.activeQuadrant === "green" || this.activeQuadrant === "blue"
          ? "Energy -∞"
          : "Energy +∞";
      },
      pleasantnessAxisLabel() {
        return this.activeQuadrant === "red" || this.activeQuadrant === "blue"
          ? "Pleasantness -∞"
          : "Pleasantness +∞";
      },
      axisValues(axis, cell) {
        const quadrant = this.activeQuadrant || (cell && cell.quadrant);
        const cells = quadrant ? this.catalog.filter(item => item.quadrant === quadrant) : this.catalog;
        const values = [...new Set(cells.map(item => Number(item[axis])))];
        return axis === "energy" ? values.sort((a, b) => b - a) : values.sort((a, b) => a - b);
      },
      axisPercent(axis, value, cell) {
        const values = this.axisValues(axis, cell);
        const index = values.indexOf(Number(value));
        if (index < 0 || values.length === 0) return 50;
        return ((index + 0.5) / values.length) * 100;
      },
      axisEnergy() {
        const cell = this.previewCell();
        if (!cell) return 50;
        return this.axisPercent("energy", cell.energy, cell);
      },
      axisPleasantness() {
        const cell = this.previewCell();
        if (!cell) return 50;
        return this.axisPercent("pleasantness", cell.pleasantness, cell);
      },
      activeColumns() {
        if (!this.activeQuadrant) return this.axis.columns;
        return this.axisValues("pleasantness").length || 1;
      },
      hoverQuadrant(quadrant) {
        this.hoveredQuadrant = this.quadrantInfo(quadrant);
      },
      clearQuadrantHover() {
        this.hoveredQuadrant = null;
      },
      chooseQuadrant(quadrant) {
        this.activeQuadrant = quadrant;
        this.selected = null;
        this.hovered = null;
        this.hoveredQuadrant = null;
        this.stage = "moods";
        this.$nextTick(() => {
          const first = document.querySelector(`.saga-mood-cell[data-quadrant="${quadrant}"]`);
          if (first) first.focus();
        });
      },
      backToQuadrants() {
        this.stage = "quadrants";
        this.hovered = null;
        this.hoveredQuadrant = null;
        this.$nextTick(() => {
          const active = this.activeQuadrant || (this.selected && this.selected.quadrant);
          const target = active
            ? document.querySelector(`.saga-quadrant-card[data-quadrant="${active}"]`)
            : document.querySelector(".saga-quadrant-card");
          if (target) target.focus();
        });
      },
      hoverCell(energy, pleasantness) {
        const cell = findCell(this.catalog, energy, pleasantness);
        if (!cell) return;
        this.hovered = cell;
      },
      clearHover() {
        this.hovered = null;
      },
      toggleCell(energy, pleasantness) {
        const cell = findCell(this.catalog, energy, pleasantness);
        if (!cell) return;
        if (this.selected && this.selected.energy === energy && this.selected.pleasantness === pleasantness) {
          this.selected = null;
          return;
        }
        this.selected = cell;
        this.activeQuadrant = cell.quadrant;
        this.stage = "moods";
      },
      moveQuadrantFocus(event, index) {
        const keyMoves = { ArrowRight: 1, ArrowLeft: -1, ArrowDown: 2, ArrowUp: -2 };
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          const quadrant = this.quadrants[index];
          if (quadrant) this.chooseQuadrant(quadrant.key);
          return;
        }
        if (!(event.key in keyMoves)) return;
        event.preventDefault();
        const next = Math.max(0, Math.min(this.quadrants.length - 1, index + keyMoves[event.key]));
        const buttons = event.currentTarget.closest(".saga-quadrant-field").querySelectorAll(".saga-quadrant-card");
        if (buttons[next]) buttons[next].focus();
      },
      moveFocus(event) {
        if (event.key === "Escape") {
          event.preventDefault();
          this.backToQuadrants();
          return;
        }
        const keyMoves = {
          ArrowRight: 1,
          ArrowLeft: -1,
          ArrowDown: this.activeColumns(),
          ArrowUp: -this.activeColumns(),
        };
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          this.toggleCell(Number(event.currentTarget.dataset.energy), Number(event.currentTarget.dataset.pleasantness));
          return;
        }
        if (!(event.key in keyMoves)) return;
        event.preventDefault();
        const buttons = Array.from(
          event.currentTarget.closest(".saga-mood-grid").querySelectorAll(".saga-mood-cell")
        ).filter(button => button.offsetParent !== null);
        const index = buttons.indexOf(event.currentTarget);
        const next = Math.max(0, Math.min(buttons.length - 1, index + keyMoves[event.key]));
        if (buttons[next]) buttons[next].focus();
      },
      finishCapture() {
        this.draftPaused = true;
        this.stage = "quadrants";
        this.activeQuadrant = null;
        this.selected = null;
        this.hovered = null;
        this.hoveredQuadrant = null;
        this.note = "";
        this.confirmation = "Entry saved.";
        localStorage.removeItem("saga.mood.draft.v1");
        this.$nextTick(() => {
          this.draftPaused = false;
          if (this.$refs.noteInput) this.$refs.noteInput.focus();
        });
        setTimeout(() => this.confirmation = "", 1800);
      },
    };
  };
})();
