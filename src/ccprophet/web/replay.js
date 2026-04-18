// ccprophet — Session Replay & Compare (PRD F9 Phase 1).
// Vanilla JS, no build step, no network outside 127.0.0.1.
//
// Depends on window.CCP, seeded by index.html with:
//   CCP.leftPane / CCP.rightPane : { draw, clear, setVisibleNodes, resetOpacity }
//   CCP.selectSession(sid)       : loads session detail + DAG into left pane
//   CCP.fetchJSON(url)           : fetch wrapper
//   CCP.onLeftLoaded / CCP.onSessionsRefreshed : hook points
//
// Replay JSON contract (see adapters/web/replay_shaper.py build_replay):
//   { timeline: [{ts, kind, phase_id, tool_name, tool_call_id,
//                  tokens, cumulative_tokens, bloat_ratio_at, bloat_spike}, ...],
//     node_snapshots: [{ts, visible_node_ids: [str,...]}, ...],
//     total_duration_sec, total_tokens, final_bloat_ratio }

(function (CCP) {
  "use strict";
  if (!CCP) { console.error("CCP namespace missing"); return; }

  var bar = document.getElementById("replay-bar");
  var slider = document.getElementById("replay-slider");
  var playBtn = document.getElementById("replay-play");
  var statusEl = document.getElementById("replay-status");
  var speedBtns = document.querySelectorAll("#replay-speed button");
  var modeDagBtn = document.getElementById("mode-dag");
  var modeReplayBtn = document.getElementById("mode-replay");
  var modeCompareBtn = document.getElementById("mode-compare");
  var mainGrid = document.getElementById("main-grid");
  var secondPicker = document.getElementById("second-session-picker");
  var rightStage = document.getElementById("stage-right");
  var leftPaneLabel = document.getElementById("pane-label-left");
  var deltaChip = document.getElementById("delta-chip");
  var timeModeWrap = document.getElementById("time-mode-wrap");
  var timeModeWall = document.getElementById("time-mode-wall");

  var SLIDER_STEPS = 1000;
  var state = {
    mode: "dag",
    leftReplay: null,
    rightReplay: null,
    speed: 1,
    playing: false,
    progress: 0,      // 0..1 along the slider
    playTimer: null,
    useWallClock: false,
  };

  function pad(n) { return n < 10 ? "0" + n : String(n); }
  function fmtElapsed(sec) {
    sec = Math.max(0, Math.floor(sec));
    var m = Math.floor(sec / 60);
    var s = sec % 60;
    return "+" + pad(m) + ":" + pad(s);
  }
  function fmtTokens(n) {
    if (n == null) return "-";
    if (n >= 1000) return (n / 1000).toFixed(1) + "k";
    return String(n);
  }

  // Find the last timeline index whose cumulative time (from step 0) is
  // <= progress * duration. Linear scan is fine — timelines are bounded by
  // tool_call count (typical < few hundred).
  function stepIndexFor(replay, progress) {
    if (!replay || !replay.timeline.length) return -1;
    var first = new Date(replay.timeline[0].ts).getTime();
    var last = new Date(replay.timeline[replay.timeline.length - 1].ts).getTime();
    var span = Math.max(last - first, 1);
    var targetMs = first + progress * span;
    var idx = -1;
    for (var i = 0; i < replay.timeline.length; i++) {
      if (new Date(replay.timeline[i].ts).getTime() <= targetMs) idx = i;
      else break;
    }
    return idx;
  }

  function applySnapshot(pane, replay, idx) {
    if (!pane || !replay) return;
    if (idx < 0) { pane.setVisibleNodes(new Set()); return; }
    var snap = replay.node_snapshots[idx];
    pane.setVisibleNodes(new Set(snap.visible_node_ids));
  }

  function currentStatus(replay, idx) {
    if (!replay || idx < 0) return "t=+00:00 - ready";
    var step = replay.timeline[idx];
    var first = new Date(replay.timeline[0].ts).getTime();
    var elapsed = (new Date(step.ts).getTime() - first) / 1000;
    var who = step.tool_name || step.phase_type || step.kind;
    var spike = step.bloat_spike ? " [SPIKE]" : "";
    return (
      "t=" + fmtElapsed(elapsed) +
      " - " + step.kind + ": " + who +
      " - cum " + fmtTokens(step.cumulative_tokens) +
      " - bloat " + (step.bloat_ratio_at != null
        ? (step.bloat_ratio_at * 100).toFixed(1) + "%" : "-") +
      spike
    );
  }

  function updateDeltaChip() {
    if (state.mode !== "compare" || !state.leftReplay || !state.rightReplay) {
      deltaChip.style.display = "none";
      return;
    }
    deltaChip.style.display = "inline-block";
    var li = stepIndexFor(state.leftReplay, state.progress);
    var ri = stepIndexFor(state.rightReplay, state.progress);
    var lRatio = li >= 0 ? state.leftReplay.timeline[li].bloat_ratio_at || 0 : 0;
    var rRatio = ri >= 0 ? state.rightReplay.timeline[ri].bloat_ratio_at || 0 : 0;
    var delta = rRatio - lRatio;
    var sign = delta > 0 ? "+" : "";
    deltaChip.textContent =
      "L: " + (lRatio * 100).toFixed(1) + "% | " +
      "R: " + (rRatio * 100).toFixed(1) + "% (" +
      "Δ " + sign + (delta * 100).toFixed(1) + "%)";
    deltaChip.className = "";
    if (Math.abs(delta) > 0.05) deltaChip.className = delta > 0 ? "bad" : "ok";
  }

  function render() {
    var lIdx = stepIndexFor(state.leftReplay, state.progress);
    applySnapshot(CCP.leftPane, state.leftReplay, lIdx);
    statusEl.textContent = currentStatus(state.leftReplay, lIdx);
    if (state.mode === "compare") {
      var rIdx = stepIndexFor(state.rightReplay, state.progress);
      applySnapshot(CCP.rightPane, state.rightReplay, rIdx);
    }
    updateDeltaChip();
  }

  function setSliderFromProgress() {
    slider.value = String(Math.round(state.progress * SLIDER_STEPS));
  }

  slider.addEventListener("input", function () {
    state.progress = Math.min(1, Math.max(0, +slider.value / SLIDER_STEPS));
    render();
  });

  playBtn.addEventListener("click", function () { togglePlay(); });

  speedBtns.forEach(function (b) {
    b.addEventListener("click", function () {
      state.speed = +b.getAttribute("data-speed") || 1;
      speedBtns.forEach(function (x) { x.classList.remove("active"); });
      b.classList.add("active");
    });
  });

  if (timeModeWall) {
    timeModeWall.addEventListener("change", function () {
      state.useWallClock = !!timeModeWall.checked;
      // Normalized vs wall-clock only affects compare: when wall-clock,
      // the slider represents real seconds on the *longer* of the two
      // sessions; when normalized, progress is 0..1 applied to each.
      render();
    });
  }

  function togglePlay() {
    state.playing = !state.playing;
    playBtn.textContent = state.playing ? "pause" : "play";
    playBtn.classList.toggle("active", state.playing);
    if (state.playing) {
      var last = performance.now();
      var tick = function () {
        if (!state.playing) return;
        var now = performance.now();
        var dt = (now - last) / 1000;
        last = now;
        var duration = activeDuration();
        if (duration <= 0) { stopPlay(); return; }
        state.progress += (dt * state.speed) / duration;
        if (state.progress >= 1) { state.progress = 1; stopPlay(); return; }
        setSliderFromProgress();
        render();
        state.playTimer = requestAnimationFrame(tick);
      };
      state.playTimer = requestAnimationFrame(tick);
    } else {
      stopPlay();
    }
  }

  function stopPlay() {
    state.playing = false;
    playBtn.textContent = "play";
    playBtn.classList.remove("active");
    if (state.playTimer) { cancelAnimationFrame(state.playTimer); state.playTimer = null; }
  }

  function activeDuration() {
    if (state.mode === "compare" && state.leftReplay && state.rightReplay) {
      if (state.useWallClock) {
        return Math.max(
          state.leftReplay.total_duration_sec,
          state.rightReplay.total_duration_sec
        ) || 1;
      }
      return 1;  // normalized progress — slider is the authoritative clock.
    }
    return (state.leftReplay && state.leftReplay.total_duration_sec) || 1;
  }

  // Mode switching --------------------------------------------------------
  function setMode(mode) {
    state.mode = mode;
    CCP.state.mode = mode;
    [modeDagBtn, modeReplayBtn, modeCompareBtn].forEach(function (b) {
      b.classList.remove("active");
      b.setAttribute("aria-selected", "false");
    });
    var activeBtn = ({
      dag: modeDagBtn,
      replay: modeReplayBtn,
      compare: modeCompareBtn,
    })[mode];
    activeBtn.classList.add("active");
    activeBtn.setAttribute("aria-selected", "true");

    stopPlay();
    state.progress = 0;
    setSliderFromProgress();

    if (mode === "dag") {
      bar.classList.remove("visible");
      secondPicker.classList.remove("visible");
      mainGrid.classList.remove("compare-mode");
      rightStage.style.display = "none";
      leftPaneLabel.style.display = "none";
      timeModeWrap.style.display = "none";
      if (CCP.leftPane) CCP.leftPane.resetOpacity();
      return;
    }

    bar.classList.add("visible");
    if (mode === "replay") {
      secondPicker.classList.remove("visible");
      mainGrid.classList.remove("compare-mode");
      rightStage.style.display = "none";
      leftPaneLabel.style.display = "none";
      timeModeWrap.style.display = "none";
      loadReplayForSelected();
    } else if (mode === "compare") {
      secondPicker.classList.add("visible");
      mainGrid.classList.add("compare-mode");
      rightStage.style.display = "block";
      leftPaneLabel.style.display = "inline-block";
      leftPaneLabel.textContent = "L";
      timeModeWrap.style.display = "inline-flex";
      populateSecondPicker();
      loadReplayForSelected();
      if (secondPicker.value) loadRightSession(secondPicker.value);
    }
  }

  modeDagBtn.addEventListener("click", function () { setMode("dag"); });
  modeReplayBtn.addEventListener("click", function () { setMode("replay"); });
  modeCompareBtn.addEventListener("click", function () { setMode("compare"); });

  // Replay loading --------------------------------------------------------
  function loadReplayForSelected() {
    var sid = CCP.state.selected;
    if (!sid) return;
    CCP.fetchJSON("/api/sessions/" + encodeURIComponent(sid) + "/replay")
      .then(function (rep) {
        state.leftReplay = rep;
        state.progress = 0;
        setSliderFromProgress();
        render();
      })
      .catch(function (err) {
        console.error("replay load failed", err);
        statusEl.textContent = "replay load failed: " + err.message;
      });
  }

  function loadRightSession(sid) {
    if (!sid) return;
    Promise.all([
      CCP.fetchJSON("/api/sessions/" + encodeURIComponent(sid) + "/dag"),
      CCP.fetchJSON("/api/sessions/" + encodeURIComponent(sid) + "/replay"),
    ]).then(function (out) {
      CCP.rightPane.draw(out[0]);
      state.rightReplay = out[1];
      CCP.state.right = { sid: sid, dag: out[0] };
      state.progress = 0;
      setSliderFromProgress();
      render();
    }).catch(function (err) {
      console.error("right session load failed", err);
    });
  }

  function populateSecondPicker() {
    var rows = CCP.allSessions || [];
    var current = secondPicker.value;
    secondPicker.innerHTML = "";
    var added = 0;
    rows.forEach(function (s) {
      if (s.session_id === CCP.state.selected) return;
      var opt = document.createElement("option");
      opt.value = s.session_id;
      opt.textContent = s.session_id.slice(0, 12) + " · " + s.model;
      secondPicker.appendChild(opt);
      added++;
    });
    if (added === 0) {
      var opt = document.createElement("option");
      opt.value = "";
      opt.textContent = "(no other sessions)";
      secondPicker.appendChild(opt);
    } else if (current) {
      secondPicker.value = current;
    }
  }

  secondPicker.addEventListener("change", function () {
    loadRightSession(secondPicker.value);
  });

  // Hook into shared pipeline ---------------------------------------------
  CCP.onLeftLoaded = function () {
    if (state.mode === "replay" || state.mode === "compare") loadReplayForSelected();
  };
  CCP.onSessionsRefreshed = function () {
    if (state.mode === "compare") populateSecondPicker();
  };
})(window.CCP);
