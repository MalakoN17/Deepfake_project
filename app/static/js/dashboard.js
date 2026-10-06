// Dashboard charts (Chart.js) and auto-refresh every 5 seconds from /api/dashboard
(() => {
  const initial = JSON.parse(document.getElementById("dash-data").textContent);
  const css = getComputedStyle(document.documentElement);
  const c = (name) => css.getPropertyValue(name).trim();
  Chart.defaults.color = c("--muted");
  Chart.defaults.borderColor = c("--line");
  Chart.defaults.font.family = "IBM Plex Sans, sans-serif";

  const trend = new Chart(document.getElementById("trend"), {
    type: "line",
    data: { labels: initial.trend.labels, datasets: [{ label: "Deepfake risk %", data: initial.trend.risk,
      borderColor: c("--accent"), backgroundColor: "rgba(91,141,239,.12)", fill: true, tension: 0.25,
      pointRadius: 3, pointBackgroundColor: initial.trend.risk.map((v) => v >= 70 ? c("--bad") : v >= 31 ? c("--warn") : c("--ok")) }] },
    options: { aspectRatio: 2.4, scales: { y: { min: 0, max: 100 } }, plugins: { legend: { display: false } } },
  });
  const split = new Chart(document.getElementById("split"), {
    type: "doughnut",
    data: { labels: ["Approved", "Suspicious", "Rejected"],
      datasets: [{ data: [initial.approved, initial.suspicious, initial.rejected],
        backgroundColor: [c("--ok"), c("--warn"), c("--bad")], borderWidth: 0 }] },
    options: { aspectRatio: 1.25, cutout: "68%", plugins: { legend: { position: "bottom" } } },
  });

  const cls = { Approved: "ok", Suspicious: "warn", Rejected: "bad" };
  const esc = (s) => String(s).replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[ch]);
  const riskCell = (v) => { const k = v >= 70 ? "bad" : v >= 31 ? "warn" : "ok";
    return `<span class="riskbar ${k}"><span style="width:${Math.round(v)}%"></span></span><span class="num">${Math.round(v)}%</span>`; };
  const ms = (v) => (v >= 1000 ? `${(v / 1000).toFixed(2)} s` : `${Math.round(v)} ms`);

  async function refresh() {
    try {
      const res = await fetch("/api/dashboard", { headers: { Accept: "application/json" } });
      if (!res.ok) return;
      const d = await res.json();
      document.querySelectorAll("[data-k]").forEach((el) => { el.textContent = d[el.dataset.k]; });
      document.getElementById("live-dot").classList.toggle("live", d.live_sessions > 0);
      document.getElementById("live-status").textContent = `${d.live_sessions} live session${d.live_sessions === 1 ? "" : "s"} running`;
      trend.data.labels = d.trend.labels; trend.data.datasets[0].data = d.trend.risk;
      trend.data.datasets[0].pointBackgroundColor = d.trend.risk.map((v) => v >= 70 ? c("--bad") : v >= 31 ? c("--warn") : c("--ok"));
      trend.update("none");
      split.data.datasets[0].data = [d.approved, d.suspicious, d.rejected]; split.update("none");
      if (d.recent.length) {
        document.getElementById("recent").innerHTML = d.recent.map((r) => `<tr><td>${esc(r.user)}</td>
          <td><a href="/analysis/${r.meeting_id}">${esc(r.meeting)}</a></td><td>${riskCell(r.risk)}</td>
          <td class="num">${Math.round(r.trust)}%</td><td><span class="badge-r ${cls[r.result]}">${r.result}</span></td>
          <td class="num">${ms(r.processing_ms)}</td><td class="num">${r.timestamp}</td></tr>`).join("");
      }
    } catch (e) { /* offline - try again next cycle */ }
  }
  setInterval(refresh, 5000);
})();
