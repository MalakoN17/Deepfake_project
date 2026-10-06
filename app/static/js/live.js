// Live analysis: capture ~1 frame/second from the camera or a shared window,
// send it to the server, and show the score, face box and risk timeline.
(() => {
  const cfg = JSON.parse(document.getElementById("live-config").textContent);
  const csrf = document.querySelector('meta[name="csrf-token"]').content;
  const $ = (id) => document.getElementById(id);
  const video = $("video"), overlay = $("overlay"), timeline = $("timeline");
  const COLORS = { Approved: "#34c28a", Suspicious: "#edb24a", Rejected: "#ef6461" };
  const CLASS = { Approved: "ok", Suspicious: "warn", Rejected: "bad" };
  const INTERVAL_MS = 1000, MAX_POINTS = 60;
  let stream = null, meetingId = null, timer = null, busy = false, points = [], lastBox = null, lastResult = null;

  const url = (template, id) => template.replace("/0/", `/${id}/`);
  const setError = (msg) => { $("error").textContent = msg || ""; };
  const fmtMs = (v) => (v == null ? "-" : v >= 1000 ? `${(v / 1000).toFixed(2)} s` : `${Math.round(v)} ms`);
  const setMeter = (key, value) => {
    $("m-" + key).style.width = value == null ? "0%" : `${Math.max(0, Math.min(100, value))}%`;
    $("v-" + key).textContent = value == null ? "-" : `${Math.round(value)}`;
  };

  async function getStream(source) {
    if (!window.isSecureContext) {
      throw new Error("The browser only allows camera and screen capture on https:// or on localhost.");
    }
    if (source === "screen") {
      return navigator.mediaDevices.getDisplayMedia({ video: { frameRate: 5 }, audio: false });
    }
    try {
      return await navigator.mediaDevices.getUserMedia({ video: { width: 1280, height: 720 }, audio: false });
    } catch (err) {
      if (err.name === "NotAllowedError") throw err;
      // Some webcams refuse a specific resolution - retry with the camera's default mode
      return navigator.mediaDevices.getUserMedia({ video: true, audio: false });
    }
  }

  async function start() {
    setError("");
    const source = document.querySelector('input[name="source"]:checked').value;
    try {
      stream = await getStream(source);
    } catch (err) {
      const messages = {
        NotAllowedError: "Permission was denied. Allow camera access in the browser and try again.",
        NotReadableError: "The camera is busy or blocked. Close Zoom, Teams or other apps using it, check the camera privacy switch, then reload the page.",
        NotFoundError: "No camera was found on this computer.",
      };
      setError(messages[err.name] || err.message || "Could not open the video source.");
      return;
    }
    video.srcObject = stream;
    stream.getVideoTracks()[0].addEventListener("ended", stop);   // user stopped sharing
    $("stage-empty").hidden = true;
    const res = await fetch(cfg.start_url, {
      method: "POST", headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
      body: JSON.stringify({ meeting_name: $("meeting_name").value, platform: $("platform").value,
        identity_id: $("identity").value, source }),
    });
    if (!res.ok) { setError("The server could not start the session."); stopTracks(); return; }
    meetingId = (await res.json()).meeting_id;
    points = [];
    $("start").disabled = true; $("stop").disabled = false;
    for (const el of document.querySelectorAll("#setup input, #setup select")) el.disabled = true;
    timer = setInterval(tick, INTERVAL_MS);
  }

  function captureFrame() {
    const w = video.videoWidth, h = video.videoHeight;
    if (!w || !h) return Promise.resolve(null);
    const scale = Math.min(1, 800 / w);                    // downscale: less upload, face still large enough
    const c = document.createElement("canvas");
    c.width = Math.round(w * scale); c.height = Math.round(h * scale);
    c.getContext("2d").drawImage(video, 0, 0, c.width, c.height);
    return new Promise((resolve) => c.toBlob(resolve, "image/jpeg", 0.85));
  }

  async function tick() {
    if (busy || !meetingId) return;          // never queue frames if the server is slower than 1/s
    busy = true;
    try {
      const blob = await captureFrame();
      if (!blob) return;
      const form = new FormData();
      form.append("frame", blob, "frame.jpg");
      const t0 = performance.now();
      const res = await fetch(url(cfg.frame_url, meetingId), { method: "POST", headers: { "X-CSRFToken": csrf }, body: form });
      const rtt = performance.now() - t0;
      if (!res.ok) { setError(`Frame rejected by the server (HTTP ${res.status}).`); return; }
      update(await res.json(), rtt);
    } catch (err) {
      setError("Connection to the server failed. Retrying...");
    } finally {
      busy = false;
    }
  }

  function update(d, rtt) {
    setError("");
    lastBox = d.box; lastResult = d.result;
    $("verdict").className = "verdict " + CLASS[d.result];
    $("verdict-label").textContent = d.face_found ? "Current assessment (smoothed)" : "No face in this frame";
    $("result").textContent = d.result;
    $("reasons").textContent = d.reasons.join(". ");
    setMeter("risk", d.face_found ? d.smoothed_risk : null);
    setMeter("trust", d.trust);
    setMeter("id", d.identity_match);
    setMeter("q", d.face_found ? d.quality : null);
    $("l-face").textContent = fmtMs(d.face_ms);
    $("l-inf").textContent = fmtMs(d.inference_ms);
    $("l-server").textContent = fmtMs(d.server_ms);
    $("l-rtt").textContent = fmtMs(rtt);
    $("first").textContent = fmtMs(d.first_score_ms);
    $("frames").textContent = d.frames;
    if (d.saved && d.saved.alert) {
      const t = $("alert-toast");
      t.textContent = `${d.saved.alert.severity}: ${d.saved.alert.message}`;
      t.classList.remove("show"); void t.offsetWidth; t.classList.add("show");
    }
    points.push({ frame: d.frame_risk, smooth: d.face_found ? d.smoothed_risk : null, result: d.result });
    if (points.length > MAX_POINTS) points.shift();
    drawTimeline();
  }

  function drawOverlay() {
    const r = overlay.getBoundingClientRect(), dpr = window.devicePixelRatio || 1;
    overlay.width = r.width * dpr; overlay.height = r.height * dpr;
    const ctx = overlay.getContext("2d");
    ctx.clearRect(0, 0, overlay.width, overlay.height);
    if (lastBox && video.videoWidth) {
      // the video is letterboxed ("object-fit: contain") - map normalised box to the drawn area
      const s = Math.min(overlay.width / video.videoWidth, overlay.height / video.videoHeight);
      const vw = video.videoWidth * s, vh = video.videoHeight * s;
      const ox = (overlay.width - vw) / 2, oy = (overlay.height - vh) / 2;
      const [x1, y1, x2, y2] = lastBox;
      ctx.strokeStyle = COLORS[lastResult] || "#5b8def"; ctx.lineWidth = 3 * dpr;
      ctx.strokeRect(ox + x1 * vw, oy + y1 * vh, (x2 - x1) * vw, (y2 - y1) * vh);
      ctx.fillStyle = ctx.strokeStyle; ctx.font = `${13 * dpr}px IBM Plex Sans, sans-serif`;
      ctx.fillText(lastResult, ox + x1 * vw, oy + y1 * vh - 6 * dpr);
    }
    requestAnimationFrame(drawOverlay);
  }

  function drawTimeline() {
    const dpr = window.devicePixelRatio || 1, W = timeline.clientWidth * dpr, H = timeline.clientHeight * dpr;
    timeline.width = W; timeline.height = H;
    const ctx = timeline.getContext("2d"), pad = 6 * dpr, step = W / MAX_POINTS;
    const y = (v) => H - pad - (v / 100) * (H - 2 * pad);
    ctx.setLineDash([4 * dpr, 4 * dpr]); ctx.lineWidth = dpr;
    for (const [v, c] of [[cfg.suspicious, COLORS.Suspicious], [cfg.rejected, COLORS.Rejected]]) {
      ctx.strokeStyle = c + "99"; ctx.beginPath(); ctx.moveTo(0, y(v)); ctx.lineTo(W, y(v)); ctx.stroke();
    }
    ctx.setLineDash([]);
    ctx.font = `${11 * dpr}px IBM Plex Sans, sans-serif`;
    ctx.fillStyle = "#8ea3b8";
    ctx.fillText(`${cfg.rejected}%`, W - 34 * dpr, y(cfg.rejected) - 4 * dpr);
    ctx.fillText(`${cfg.suspicious}%`, W - 34 * dpr, y(cfg.suspicious) - 4 * dpr);
    points.forEach((p, i) => {
      if (p.frame == null) return;
      ctx.fillStyle = (COLORS[p.result] || "#8ea3b8") + "66";
      ctx.fillRect(i * step + step * 0.2, y(p.frame), step * 0.6, H - pad - y(p.frame));
    });
    ctx.strokeStyle = "#e4ecf4"; ctx.lineWidth = 2 * dpr; ctx.beginPath();
    let started = false;
    points.forEach((p, i) => {
      if (p.smooth == null) { started = false; return; }
      const x = i * step + step / 2;
      started ? ctx.lineTo(x, y(p.smooth)) : ctx.moveTo(x, y(p.smooth));
      started = true;
    });
    ctx.stroke();
  }

  function stopTracks() {
    if (stream) stream.getTracks().forEach((t) => t.stop());
    stream = null;
  }

  async function stop() {
    clearInterval(timer); timer = null;
    stopTracks();
    if (!meetingId) return;
    const id = meetingId; meetingId = null;
    $("stop").disabled = true;
    const res = await fetch(url(cfg.stop_url, id), { method: "POST", headers: { "X-CSRFToken": csrf } });
    if (res.ok) window.location = (await res.json()).redirect;
    else setError("The session could not be saved.");
  }

  $("start").addEventListener("click", start);
  $("stop").addEventListener("click", stop);
  window.addEventListener("resize", drawTimeline);
  drawTimeline();
  requestAnimationFrame(drawOverlay);
})();
