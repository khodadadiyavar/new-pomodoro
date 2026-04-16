(function () {
  const DEFAULT_IDLE_STATUS = "One active focus session is allowed per user.";
  const POLL_INTERVAL_MS = 5000;

  function readActiveSession(root) {
    try {
      return JSON.parse(root.dataset.activeSession || "{}");
    } catch (error) {
      return {};
    }
  }

  function hasActiveSession(current) {
    return Boolean(current && current.id);
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

  function formatSeconds(totalSeconds) {
    const seconds = Math.max(0, Math.floor(totalSeconds));
    const minutes = Math.floor(seconds / 60);
    const remainder = seconds % 60;
    return `${String(minutes).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`;
  }

  const root = document.querySelector("[data-focus-root]");
  if (!root) {
    return;
  }

  const timerEl = document.getElementById("focus-timer");
  const labelEl = document.getElementById("focus-state-label");
  const statusEl = document.getElementById("focus-status-message");
  const noteEl = document.getElementById("session-note");
  const goalSelect = document.getElementById("goal-id");
  const minutesInput = document.getElementById("planned-minutes");
  const startButton = document.getElementById("start-session-button");
  const pauseButton = document.getElementById("pause-session-button");
  const resumeButton = document.getElementById("resume-session-button");
  const stopButton = document.getElementById("stop-session-button");
  const discardButton = document.getElementById("discard-session-button");

  let session = readActiveSession(root);
  let tickHandle = null;
  let refreshHandle = null;
  let idleStatusMessage = DEFAULT_IDLE_STATUS;
  let timeoutNotificationSessionId = null;

  function elapsedSeconds(current) {
    if (!hasActiveSession(current)) {
      return 0;
    }
    let elapsed = Number(current.elapsed_seconds || 0);
    if (current.state === "running" && current.last_state_change_at) {
      const then = parseTimestamp(current.last_state_change_at);
      if (then && !Number.isNaN(then.getTime())) {
        elapsed += Math.max(0, Math.floor((Date.now() - then.getTime()) / 1000));
      }
    }
    return elapsed;
  }

  function remainingSeconds(current) {
    return Number(current.planned_minutes || 25) * 60 - elapsedSeconds(current);
  }

  function idleMessageForTransition(payload) {
    if (!payload.just_completed) {
      return DEFAULT_IDLE_STATUS;
    }
    if (payload.ended_reason === "auto_finished") {
      return "Timer complete. Session auto-finished and logged to the weekly scoreboard.";
    }
    return "Session ended.";
  }

  function notifyTimeout(sessionId) {
    if (!sessionId || timeoutNotificationSessionId === sessionId) {
      return;
    }
    timeoutNotificationSessionId = sessionId;
    if (typeof window.Notification === "undefined") {
      return;
    }
    if (window.Notification.permission !== "granted") {
      return;
    }
    new window.Notification("Focus timer complete", {
      body: "Your focus block finished and will auto-log shortly.",
    });
  }

  async function primeNotificationPermission() {
    if (typeof window.Notification === "undefined") {
      return;
    }
    if (window.Notification.permission !== "default") {
      return;
    }
    try {
      await window.Notification.requestPermission();
    } catch (error) {
      // Ignore permission errors and keep the timer working.
    }
  }

  function syncView() {
    if (!hasActiveSession(session)) {
      labelEl.textContent = "Ready for a focus block";
      timerEl.textContent = formatSeconds(Number(minutesInput.value || 25) * 60);
      statusEl.textContent = idleStatusMessage;
      return;
    }

    const remaining = remainingSeconds(session);
    if (session.state === "paused") {
      labelEl.textContent = "Session paused";
      timerEl.textContent = formatSeconds(remaining);
      statusEl.textContent = "Goal session is paused. Resume here when you are ready to continue.";
      return;
    }

    if (remaining <= 0) {
      labelEl.textContent = "Focus block complete";
      timerEl.textContent = "00:00";
      statusEl.textContent = "Focus timer complete. Checking session status...";
      return;
    }

    labelEl.textContent = "Focus block in progress";
    timerEl.textContent = formatSeconds(remaining);
    statusEl.textContent = `Goal session is ${session.state}. Completed sessions update the weekly scoreboard automatically.`;
  }

  function startTicking() {
    if (tickHandle) {
      clearInterval(tickHandle);
    }
    tickHandle = setInterval(syncView, 1000);
  }

  async function fetchSessionStatus() {
    const response = await fetch("/api/session-status", {
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
    if (!response.ok) {
      throw new Error(`Request failed with ${response.status}`);
    }
    return response.json();
  }

  function startRefreshing() {
    if (refreshHandle) {
      clearInterval(refreshHandle);
    }
    refreshHandle = setInterval(function () {
      void refreshSessionStatus();
    }, POLL_INTERVAL_MS);
  }

  async function refreshSessionStatus() {
    const previousSession = session;

    try {
      const payload = await fetchSessionStatus();
      const nextSession = payload.session || {};

      if (payload.just_completed) {
        idleStatusMessage = idleMessageForTransition(payload);
        if (payload.ended_reason === "auto_finished") {
          notifyTimeout(previousSession.id);
        }
      } else if (hasActiveSession(nextSession)) {
        idleStatusMessage = DEFAULT_IDLE_STATUS;
      } else {
        idleStatusMessage = idleMessageForTransition(payload);
      }

      session = nextSession;
      syncView();
    } catch (error) {
      // Keep the local countdown moving if background refresh fails.
    }
  }

  async function postForm(url, data) {
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams(data),
    });
    if (!response.ok) {
      throw new Error(`Request failed with ${response.status}`);
    }
    return response.json();
  }

  startButton.addEventListener("click", async function () {
    try {
      const payload = await postForm("/api/sessions/start", {
        goal_id: goalSelect.value,
        planned_minutes: minutesInput.value,
      });
      session = payload.session || {};
      idleStatusMessage = DEFAULT_IDLE_STATUS;
      timeoutNotificationSessionId = null;
      syncView();
      await primeNotificationPermission();
    } catch (error) {
      statusEl.textContent = error.message;
    }
  });

  pauseButton.addEventListener("click", async function () {
    if (!hasActiveSession(session)) {
      return;
    }
    try {
      const payload = await postForm(`/api/sessions/${session.id}/pause`, {});
      session = payload.session || {};
      syncView();
    } catch (error) {
      statusEl.textContent = error.message;
    }
  });

  resumeButton.addEventListener("click", async function () {
    if (!hasActiveSession(session)) {
      return;
    }
    try {
      const payload = await postForm(`/api/sessions/${session.id}/resume`, {});
      session = payload.session || {};
      syncView();
    } catch (error) {
      statusEl.textContent = error.message;
    }
  });

  stopButton.addEventListener("click", async function () {
    if (!hasActiveSession(session)) {
      return;
    }
    try {
      const payload = await postForm(`/api/sessions/${session.id}/stop`, {
        note: noteEl.value,
      });
      session = {};
      noteEl.value = "";
      idleStatusMessage = `Session stopped and logged for ${payload.session.actual_minutes} minutes.`;
      timeoutNotificationSessionId = payload.session.id;
      syncView();
    } catch (error) {
      statusEl.textContent = error.message;
    }
  });

  discardButton.addEventListener("click", async function () {
    if (!hasActiveSession(session)) {
      return;
    }
    try {
      await postForm(`/api/sessions/${session.id}/discard`, {});
      session = {};
      noteEl.value = "";
      idleStatusMessage = "Session discarded and excluded from the scoreboard.";
      syncView();
    } catch (error) {
      statusEl.textContent = error.message;
    }
  });

  minutesInput.addEventListener("input", syncView);

  syncView();
  startTicking();
  startRefreshing();
  void refreshSessionStatus();
})();
