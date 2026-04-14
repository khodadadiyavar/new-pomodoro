(function () {
  function readActiveSession(root) {
    try {
      return JSON.parse(root.dataset.activeSession || "{}");
    } catch (error) {
      return {};
    }
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
  const completeButton = document.getElementById("complete-session-button");
  const abandonButton = document.getElementById("abandon-session-button");

  let session = readActiveSession(root);
  let tickHandle = null;

  function elapsedSeconds(current) {
    if (!current || !current.id) {
      return 0;
    }
    let elapsed = Number(current.elapsed_seconds || 0);
    if (current.state === "running" && current.last_state_change_at) {
      const then = new Date(current.last_state_change_at);
      elapsed += Math.max(0, Math.floor((Date.now() - then.getTime()) / 1000));
    }
    return elapsed;
  }

  function remainingSeconds(current) {
    return Number(current.planned_minutes || 25) * 60 - elapsedSeconds(current);
  }

  function syncView() {
    if (!session || !session.id) {
      labelEl.textContent = "Ready for a focus block";
      timerEl.textContent = formatSeconds(Number(minutesInput.value || 25) * 60);
      statusEl.textContent = "One active focus session is allowed per user.";
      return;
    }
    const remaining = remainingSeconds(session);
    labelEl.textContent =
      session.state === "paused" ? "Session paused" : "Focus block in progress";
    timerEl.textContent = formatSeconds(remaining);
    statusEl.textContent = `Goal session is ${session.state}. Completed sessions update the weekly scoreboard automatically.`;
  }

  function startTicking() {
    if (tickHandle) {
      clearInterval(tickHandle);
    }
    tickHandle = setInterval(syncView, 1000);
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
      session = payload.session;
      syncView();
    } catch (error) {
      statusEl.textContent = error.message;
    }
  });

  pauseButton.addEventListener("click", async function () {
    if (!session.id) {
      return;
    }
    const payload = await postForm(`/api/sessions/${session.id}/pause`, {});
    session = payload.session;
    syncView();
  });

  resumeButton.addEventListener("click", async function () {
    if (!session.id) {
      return;
    }
    const payload = await postForm(`/api/sessions/${session.id}/resume`, {});
    session = payload.session;
    syncView();
  });

  completeButton.addEventListener("click", async function () {
    if (!session.id) {
      return;
    }
    const payload = await postForm(`/api/sessions/${session.id}/complete`, {
      note: noteEl.value,
    });
    session = {};
    noteEl.value = "";
    statusEl.textContent = `Session completed and logged for ${payload.session.actual_minutes} minutes.`;
    syncView();
  });

  abandonButton.addEventListener("click", async function () {
    if (!session.id) {
      return;
    }
    await postForm(`/api/sessions/${session.id}/abandon`, {});
    session = {};
    noteEl.value = "";
    statusEl.textContent = "Session abandoned and excluded from the scoreboard.";
    syncView();
  });

  syncView();
  startTicking();
})();
