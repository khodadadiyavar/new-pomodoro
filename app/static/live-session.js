(function () {
  const POLL_INTERVAL_MS = 5000;

  function parseStateRoot() {
    const node = document.querySelector("[data-live-session-state]");
    if (!node) {
      return null;
    }
    try {
      return JSON.parse(node.dataset.liveSession || "{}");
    } catch (error) {
      return null;
    }
  }

  function parseTimestamp(value) {
    if (!value) {
      return null;
    }
    if (/[zZ]|[+-]\d\d:\d\d$/.test(value)) {
      return new Date(value);
    }
    return new Date(`${value}Z`);
  }

  function hasSession(payload) {
    return Boolean(payload && payload.session && payload.session.id);
  }

  function elapsedSeconds(payload) {
    if (!hasSession(payload)) {
      return 0;
    }
    let elapsed = Number(payload.session.elapsed_seconds || 0);
    if (payload.session.state === "running" && payload.session.last_state_change_at) {
      const then = parseTimestamp(payload.session.last_state_change_at);
      if (then && !Number.isNaN(then.getTime())) {
        elapsed += Math.max(0, Math.floor((Date.now() - then.getTime()) / 1000));
      }
    }
    return elapsed;
  }

  function remainingSeconds(payload) {
    if (!hasSession(payload)) {
      return 0;
    }
    const plannedSeconds = Number(payload.session.planned_minutes || 25) * 60;
    return Math.max(0, plannedSeconds - elapsedSeconds(payload));
  }

  function formatSeconds(totalSeconds) {
    const seconds = Math.max(0, Math.floor(totalSeconds));
    const minutes = Math.floor(seconds / 60);
    const remainder = seconds % 60;
    return `${String(minutes).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`;
  }

  function updateCountdowns(payload) {
    const countdown = hasSession(payload) ? formatSeconds(remainingSeconds(payload)) : "--:--";
    document.querySelectorAll("[data-live-session-countdown]").forEach(function (node) {
      node.textContent = countdown;
    });

    const stateText = hasSession(payload)
      ? `Session is ${payload.session.state}. Jump back into focus mode to pause, stop, or add a note.`
      : "No live session.";

    document.querySelectorAll("[data-live-session-state-text]").forEach(function (node) {
      node.textContent = stateText;
    });

    const bar = document.querySelector("[data-live-session-bar]");
    if (bar) {
      bar.hidden = !hasSession(payload);
    }
  }

  async function refreshPayload() {
    const response = await fetch("/api/session-status", {
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
    if (!response.ok) {
      throw new Error(`Request failed with ${response.status}`);
    }
    return response.json();
  }

  let payload = parseStateRoot();
  if (!payload) {
    return;
  }

  updateCountdowns(payload);
  setInterval(function () {
    updateCountdowns(payload);
  }, 1000);

  setInterval(async function () {
    try {
      payload = await refreshPayload();
      updateCountdowns(payload);
    } catch (error) {
      // Leave the local counter running if the refresh request fails.
    }
  }, POLL_INTERVAL_MS);
})();
