// Renders agent chart blocks:
//   <script type="application/json" data-chart data-height="320" data-caption="...">{ Chart.js config }</script>
(function () {
  if (typeof Chart === "undefined") return;

  const css = getComputedStyle(document.documentElement);
  const token = (name) => css.getPropertyValue(name).trim();
  const palette = [1, 2, 3, 4, 5, 6].map((i) => token(`--chart-${i}`));
  const PER_POINT = new Set(["pie", "doughnut", "polarArea"]);

  Chart.defaults.color = token("--muted");
  Chart.defaults.borderColor = token("--border");
  Chart.defaults.font.family = token("--font");
  Chart.defaults.plugins.legend.labels.usePointStyle = true;

  const alpha = (hex, a) => {
    const m = /^#([0-9a-f]{6})$/i.exec(hex);
    if (!m) return hex;
    const n = parseInt(m[1], 16);
    return `rgba(${n >> 16}, ${(n >> 8) & 255}, ${n & 255}, ${a})`;
  };

  function applyPalette(cfg) {
    const datasets = (cfg.data && cfg.data.datasets) || [];
    datasets.forEach((ds, i) => {
      const type = ds.type || cfg.type;
      if (PER_POINT.has(type)) {
        if (!ds.backgroundColor) {
          const n = (ds.data || []).length;
          ds.backgroundColor = Array.from({ length: n }, (_, j) => palette[j % palette.length]);
        }
        if (!ds.borderColor) ds.borderColor = token("--surface");
        return;
      }
      const color = palette[i % palette.length];
      if (!ds.borderColor) ds.borderColor = color;
      if (!ds.backgroundColor) ds.backgroundColor = type === "line" ? alpha(color, 0.15) : alpha(color, 0.85);
      if (type === "bar" && ds.borderRadius === undefined) ds.borderRadius = 4;
      if (type === "line" && ds.tension === undefined) ds.tension = 0.3;
    });
  }

  document.querySelectorAll('script[type="application/json"][data-chart]').forEach((el) => {
    const fig = document.createElement("figure");
    fig.className = "chart";
    el.after(fig);

    let cfg;
    try {
      cfg = JSON.parse(el.textContent);
    } catch (err) {
      fig.innerHTML = "";
      fig.textContent = `Chart could not be rendered: ${err.message}`;
      fig.classList.add("chart-error");
      return;
    }

    const box = document.createElement("div");
    box.className = "chart-canvas";
    box.style.height = `${parseInt(el.dataset.height, 10) || 320}px`;
    const canvas = document.createElement("canvas");
    box.appendChild(canvas);
    fig.appendChild(box);

    if (el.dataset.caption) {
      const cap = document.createElement("figcaption");
      cap.textContent = el.dataset.caption;
      fig.appendChild(cap);
    }

    cfg.options = Object.assign({ responsive: true, maintainAspectRatio: false }, cfg.options || {});
    applyPalette(cfg);
    try {
      new Chart(canvas, cfg);
    } catch (err) {
      fig.textContent = `Chart could not be rendered: ${err.message}`;
      fig.classList.add("chart-error");
    }
  });
})();
