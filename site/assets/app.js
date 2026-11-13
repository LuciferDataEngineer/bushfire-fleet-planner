function fitMap() {
  const frame = document.querySelector("[data-map-frame]");
  if (!frame) return;
  const svg = frame.querySelector("svg");
  if (!svg) return;
  const width = frame.clientWidth;
  if (!width) {
    requestAnimationFrame(fitMap);
    return;
  }
  const box = svg.viewBox && svg.viewBox.baseVal;
  if (!box || !box.width) return;
  svg.style.width = "100%";
  svg.style.height = Math.round((width * box.height) / box.width) + "px";
}

function applyMode(mode) {
  document.querySelectorAll("#aus-map path.region").forEach(function (path) {
    const fill = path.getAttribute("data-fill-" + mode);
    if (fill) path.setAttribute("fill", fill);
  });
  document.querySelectorAll("[data-chart-panel]").forEach(function (panel) {
    panel.hidden = panel.getAttribute("data-chart-panel") !== mode;
  });
  document.querySelectorAll("[data-legend]").forEach(function (panel) {
    panel.hidden = panel.getAttribute("data-legend") !== mode;
  });
  document.querySelectorAll(".pills button").forEach(function (button) {
    button.setAttribute("aria-pressed", button.getAttribute("data-mode") === mode ? "true" : "false");
  });
  fitMap();
}

document.addEventListener("DOMContentLoaded", function () {
  fitMap();
  document.querySelectorAll(".pills button").forEach(function (button) {
    button.addEventListener("click", function () {
      applyMode(button.getAttribute("data-mode"));
    });
  });
});
window.addEventListener("resize", fitMap);
window.addEventListener("pageshow", fitMap);
