// ccprophet — Pattern Diff panel (PRD F9 / FR-9.3).
// Vanilla JS, no build step. Loads after replay.js.
//
// Wires a small toggleable panel into Compare mode that fetches
//   GET /api/sessions/{L}/pattern-diff?against={R}
// and renders the structured findings alongside the delta chip.

(function (CCP) {
  "use strict";
  if (!CCP) { console.error("CCP namespace missing (pattern_diff.js)"); return; }

  var SEVERITY_COLORS = {
    critical: "#e74c3c",
    warn: "#f39c12",
    info: "#3498db",
  };

  var bar = document.getElementById("replay-bar");
  var deltaChip = document.getElementById("delta-chip");
  if (!bar || !deltaChip) return;

  // Build the toggle button + panel once. We insert the button right after the
  // delta chip so it sits with the other replay controls.
  var toggleBtn = document.createElement("button");
  toggleBtn.id = "pattern-diff-toggle";
  toggleBtn.type = "button";
  toggleBtn.textContent = "\u0394 Pattern Diff";
  toggleBtn.style.cssText = [
    "background: var(--panel)",
    "color: var(--fg)",
    "border: 1px solid var(--border)",
    "padding: 2px 8px",
    "border-radius: 4px",
    "font-family: var(--font-mono)",
    "font-size: 11px",
    "cursor: pointer",
    "display: none",
  ].join(";");
  deltaChip.insertAdjacentElement("afterend", toggleBtn);

  var panel = document.createElement("div");
  panel.id = "pattern-diff-panel";
  panel.style.cssText = [
    "position: absolute",
    "right: 12px",
    "bottom: 72px",
    "width: 340px",
    "max-height: 260px",
    "overflow-y: auto",
    "background: var(--bg-elev)",
    "border: 1px solid var(--border)",
    "border-radius: 6px",
    "padding: 10px 12px",
    "font-family: var(--font-mono)",
    "font-size: 11px",
    "color: var(--fg)",
    "display: none",
    "z-index: 6",
    "box-shadow: 0 12px 28px rgba(0, 0, 0, 0.45)",
  ].join(";");
  bar.appendChild(panel);

  var state = {
    lastKey: null,   // "L||R" to skip duplicate fetches
    report: null,
    open: false,
    inFlight: false,
  };

  function pairKey() {
    var L = CCP.state.selected;
    var R = CCP.state.right && CCP.state.right.sid;
    if (!L || !R) return null;
    return L + "||" + R;
  }

  function renderPanel() {
    if (!state.report) {
      panel.innerHTML = '<div style="color: var(--fg-dim)">loading pattern diff...</div>';
      return;
    }
    var html = [];
    html.push(
      '<div style="font-weight:600;margin-bottom:6px">' +
      escapeHtml(state.report.headline) + "</div>"
    );
    if (!state.report.findings.length) {
      html.push('<div style="color: var(--fg-dim)">no findings</div>');
    } else {
      html.push('<ul style="list-style:none;padding:0;margin:0">');
      state.report.findings.forEach(function (f) {
        var color = SEVERITY_COLORS[f.severity] || "#94a3b8";
        html.push(
          '<li style="margin:4px 0;display:flex;gap:6px;align-items:flex-start">' +
          '<span style="flex:0 0 8px;height:8px;margin-top:5px;border-radius:50%;' +
          'background:' + color + '"></span>' +
          '<span><b>' + escapeHtml(f.kind) + '</b> — ' +
          escapeHtml(f.detail) + '</span></li>'
        );
      });
      html.push("</ul>");
    }
    panel.innerHTML = html.join("");
  }

  function escapeHtml(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
      })[c];
    });
  }

  function fetchDiff(force) {
    var key = pairKey();
    if (!key) { clear(); return; }
    if (!force && key === state.lastKey) return;
    state.lastKey = key;
    state.report = null;
    renderPanel();
    state.inFlight = true;
    var parts = key.split("||");
    var url =
      "/api/sessions/" + encodeURIComponent(parts[0]) +
      "/pattern-diff?against=" + encodeURIComponent(parts[1]);
    CCP.fetchJSON(url).then(function (rep) {
      state.report = rep;
      state.inFlight = false;
      renderPanel();
      // Badge the button with severity of the worst finding.
      var worst = "info";
      (rep.findings || []).forEach(function (f) {
        if (f.severity === "critical") worst = "critical";
        else if (f.severity === "warn" && worst !== "critical") worst = "warn";
      });
      toggleBtn.style.borderColor = SEVERITY_COLORS[worst] || "var(--border)";
    }).catch(function (err) {
      state.inFlight = false;
      state.report = { headline: "pattern diff load failed", findings: [
        { kind: "error", severity: "warn", detail: err.message },
      ]};
      renderPanel();
    });
  }

  function clear() {
    state.lastKey = null;
    state.report = null;
    state.open = false;
    panel.style.display = "none";
    toggleBtn.style.display = "none";
  }

  function show() {
    var mode = (CCP.state && CCP.state.mode) || "dag";
    if (mode !== "compare") { clear(); return; }
    if (!CCP.state.selected || !CCP.state.right) { clear(); return; }
    toggleBtn.style.display = "inline-block";
    fetchDiff(false);
  }

  toggleBtn.addEventListener("click", function () {
    state.open = !state.open;
    panel.style.display = state.open ? "block" : "none";
    if (state.open) fetchDiff(true);
  });

  // Hook the shared lifecycle points. We chain existing callbacks rather than
  // overwriting them so replay.js behavior is preserved.
  var prevLeftLoaded = CCP.onLeftLoaded;
  CCP.onLeftLoaded = function () {
    if (prevLeftLoaded) prevLeftLoaded.apply(null, arguments);
    show();
  };
  var prevSessionsRefreshed = CCP.onSessionsRefreshed;
  CCP.onSessionsRefreshed = function () {
    if (prevSessionsRefreshed) prevSessionsRefreshed.apply(null, arguments);
    show();
  };

  // Observe the compare-mode picker so that switching the right-hand session
  // triggers a re-fetch. The select lives inside index.html; listen for input.
  var rightPicker = document.getElementById("second-session-picker");
  if (rightPicker) {
    rightPicker.addEventListener("change", function () {
      // The right-session DAG load is async; defer fetch until CCP.state.right
      // updates. A small delay keeps us ordered behind replay.js's handler.
      setTimeout(show, 120);
    });
  }

  // Mode toggle buttons — clear when leaving compare, re-show when entering.
  ["mode-dag", "mode-replay", "mode-compare"].forEach(function (id) {
    var el = document.getElementById(id);
    if (!el) return;
    el.addEventListener("click", function () {
      setTimeout(show, 0);
    });
  });
})(window.CCP);
