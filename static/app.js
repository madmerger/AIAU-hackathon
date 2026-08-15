"use strict";

const REFRESH_MS = 30000;
const JST_OFFSET_MS = 9 * 3600 * 1000;
const charts = {};
const PALETTE = [
  "#e6d6ae", "#b39672", "#6fbf8b", "#e0a32e", "#8fb8d8", "#c9a8d8",
  "#e5716a", "#5fbfb0", "#d8b26a", "#a8c4a0", "#9aa7b4", "#f0e3c6",
];

const numberFormat = new Intl.NumberFormat("ja-JP", { maximumFractionDigits: 1 });

function fmt(value, suffix = "") {
  if (value === null || value === undefined) return "-";
  return numberFormat.format(value) + suffix;
}

function hourLabel(unixSeconds) {
  const date = new Date(unixSeconds * 1000 + JST_OFFSET_MS);
  return `${date.getUTCMonth() + 1}/${date.getUTCDate()} ${String(date.getUTCHours()).padStart(2, "0")}時`;
}

function clockLabel(unixSeconds) {
  const date = new Date(unixSeconds * 1000 + JST_OFFSET_MS);
  const pad = (n) => String(n).padStart(2, "0");
  return `${pad(date.getUTCHours())}:${pad(date.getUTCMinutes())}:${pad(date.getUTCSeconds())}`;
}

function durationLabel(seconds) {
  if (seconds === null || seconds === undefined) return "-";
  const total = Math.max(0, Math.floor(seconds));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  return `${hours}時間${String(minutes).padStart(2, "0")}分`;
}

function relativeLabel(unixSeconds) {
  if (!unixSeconds) return "-";
  const diff = Math.floor(Date.now() / 1000) - unixSeconds;
  if (diff < 60) return "たった今";
  if (diff < 3600) return `${Math.floor(diff / 60)}分前`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}時間前`;
  return `${Math.floor(diff / 86400)}日前`;
}

function kpi(label, value, hint, tone) {
  return `<div class="kpi ${tone || ""}"><div class="label">${label}</div>` +
    `<div class="value">${value}</div><div class="hint">${hint || ""}</div></div>`;
}

function renderKpis(data) {
  const t = data.totals;
  const pace = data.pace;
  const mergeTone = t.merge_rate === null ? "" : t.merge_rate >= 70 ? "good" : t.merge_rate >= 40 ? "warn" : "bad";
  document.getElementById("kpis").innerHTML = [
    kpi("総 ACU 利用量", fmt(t.acus), `1セッション平均 ${fmt(t.acus_per_session)} ACU`),
    kpi("PR マージ数", fmt(t.prs_merged), `作成 ${fmt(t.prs_created)} / オープン ${fmt(t.prs_open)}`),
    kpi("PR マージ率", t.merge_rate === null ? "-" : fmt(t.merge_rate, "%"), "マージ済 / 作成", mergeTone),
    kpi("直近1時間の ACU", fmt(pace.acus_last_full_hour), `今の時間帯 ${fmt(pace.acus_current_hour)}`),
    kpi("着地予測 ACU", fmt(pace.projected_total_acus), "直近1時間ペース換算"),
    kpi("セッション数", fmt(t.sessions), `稼働中 ${fmt(t.active_sessions)} / エラー ${fmt(t.error_sessions)}`,
      t.error_sessions > 0 ? "warn" : ""),
    kpi("参加 Org", `${fmt(t.active_orgs)} / ${fmt(t.orgs)}`, "セッション実行済 / 全Org"),
    kpi("アクティブユーザー", `${fmt(t.active_users)} / ${fmt(t.users)}`,
      `参加率 ${t.activation_rate === null ? "-" : fmt(t.activation_rate, "%")}`),
    kpi("マージPRあたり ACU", fmt(t.acus_per_merged_pr), "低いほど効率的"),
  ].join("");
}

function baseOptions(extra) {
  return Object.assign({
    responsive: true,
    maintainAspectRatio: false,
    animation: false,
    interaction: { mode: "index", intersect: false },
    plugins: { legend: { labels: { color: "#93a2b0", boxWidth: 10, font: { size: 10 } } } },
    scales: {
      x: { ticks: { color: "#93a2b0", maxRotation: 0, autoSkipPadding: 16, font: { size: 10 } }, grid: { color: "#2a3846" } },
      y: { ticks: { color: "#93a2b0", font: { size: 10 } }, grid: { color: "#2a3846" }, beginAtZero: true },
    },
  }, extra || {});
}

function upsertChart(id, config) {
  if (charts[id]) {
    const chart = charts[id];
    chart.data.labels = config.data.labels;
    chart.data.datasets.forEach((dataset, index) => {
      const next = config.data.datasets[index];
      if (next) {
        dataset.data = next.data;
        dataset.label = next.label;
      }
    });
    if (chart.data.datasets.length !== config.data.datasets.length) {
      chart.data.datasets = config.data.datasets;
    }
    chart.update("none");
    return;
  }
  charts[id] = new Chart(document.getElementById(id).getContext("2d"), config);
}

function renderMainCharts(data) {
  const labels = data.hourly.map((row) => hourLabel(row.hour));
  const dualAxis = {
    scales: {
      x: { ticks: { color: "#93a2b0", maxRotation: 0, autoSkipPadding: 16, font: { size: 10 } }, grid: { color: "#2a3846" } },
      y: { position: "left", beginAtZero: true, ticks: { color: "#93a2b0", font: { size: 10 } }, grid: { color: "#2a3846" } },
      y2: { position: "right", beginAtZero: true, ticks: { color: "#93a2b0", font: { size: 10 } }, grid: { drawOnChartArea: false } },
    },
  };

  upsertChart("chart-acu", {
    type: "bar",
    data: {
      labels,
      datasets: [
        { label: "ACU（1時間）", data: data.hourly.map((r) => r.acus), backgroundColor: "#e6d6ae99", borderColor: "#e6d6ae", borderWidth: 1, yAxisID: "y" },
        { type: "line", label: "ACU（累積）", data: data.hourly.map((r) => r.acus_cum), borderColor: "#6fbf8b", backgroundColor: "#b3967222", tension: 0.25, pointRadius: 0, borderWidth: 2, yAxisID: "y2", fill: true },
      ],
    },
    options: baseOptions(dualAxis),
  });

  upsertChart("chart-pr", {
    type: "bar",
    data: {
      labels,
      datasets: [
        { label: "マージ（1時間）", data: data.hourly.map((r) => r.prs_merged), backgroundColor: "#6fbf8b99", borderColor: "#6fbf8b", borderWidth: 1, yAxisID: "y" },
        { label: "作成（1時間）", data: data.hourly.map((r) => r.prs_created), backgroundColor: "#93a2b055", borderColor: "#93a2b0", borderWidth: 1, yAxisID: "y" },
        { type: "line", label: "マージ累積", data: data.hourly.map((r) => r.prs_merged_cum), borderColor: "#e6d6ae", tension: 0.25, pointRadius: 0, borderWidth: 2, yAxisID: "y2" },
      ],
    },
    options: baseOptions(dualAxis),
  });

  upsertChart("chart-rate", {
    type: "line",
    data: {
      labels,
      datasets: [
        { label: "マージ率（1時間）", data: data.hourly.map((r) => r.merge_rate), borderColor: "#e0a32e", tension: 0.25, pointRadius: 2, borderWidth: 2, spanGaps: true },
        { label: "マージ率（累積）", data: data.hourly.map((r) => r.merge_rate_cum), borderColor: "#6fbf8b", tension: 0.25, pointRadius: 0, borderWidth: 2, spanGaps: true },
      ],
    },
    options: baseOptions({
      scales: {
        x: { ticks: { color: "#93a2b0", maxRotation: 0, autoSkipPadding: 16, font: { size: 10 } }, grid: { color: "#2a3846" } },
        y: { beginAtZero: true, max: 100, ticks: { color: "#93a2b0", font: { size: 10 }, callback: (v) => v + "%" }, grid: { color: "#2a3846" } },
      },
    }),
  });

  const top = data.orgs.filter((org) => org.acus > 0).slice(0, 8);
  const others = data.orgs.filter((org) => org.acus > 0).slice(8);
  const cumulative = (values) => {
    let sum = 0;
    return values.map((value) => (sum += value));
  };
  const datasets = top.map((org, index) => ({
    label: org.name,
    data: cumulative(org.hourly_acus),
    borderColor: PALETTE[index % PALETTE.length],
    backgroundColor: PALETTE[index % PALETTE.length] + "44",
    fill: true,
    tension: 0.25,
    pointRadius: 0,
    borderWidth: 1.5,
  }));
  if (others.length) {
    const summed = data.hours.map((_, i) => others.reduce((acc, org) => acc + (org.hourly_acus[i] || 0), 0));
    datasets.push({
      label: `その他 (${others.length} Org)`,
      data: cumulative(summed),
      borderColor: "#93a2b0",
      backgroundColor: "#93a2b033",
      fill: true,
      tension: 0.25,
      pointRadius: 0,
      borderWidth: 1.5,
    });
  }
  upsertChart("chart-orgs", {
    type: "line",
    data: { labels, datasets },
    options: baseOptions({ scales: { x: { stacked: true, ticks: { color: "#93a2b0", maxRotation: 0, autoSkipPadding: 16, font: { size: 10 } }, grid: { color: "#2a3846" } }, y: { stacked: true, beginAtZero: true, ticks: { color: "#93a2b0", font: { size: 10 } }, grid: { color: "#2a3846" } } } }),
  });
}

function renderDonuts(data) {
  const donut = (id, source) => {
    const labels = Object.keys(source);
    upsertChart(id, {
      type: "doughnut",
      data: {
        labels,
        datasets: [{
          data: labels.map((key) => source[key]),
          backgroundColor: labels.map((_, index) => PALETTE[index % PALETTE.length]),
          borderColor: "#1c2731",
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        plugins: { legend: { position: "bottom", labels: { color: "#93a2b0", boxWidth: 10, font: { size: 10 } } } },
      },
    });
  };
  donut("chart-status", data.statuses);
  donut("chart-mode", data.modes);
}

function sparkline(values) {
  const max = Math.max(...values, 0.0001);
  return `<div class="spark">${values.map((v) => `<i style="height:${Math.max(1, (v / max) * 22)}px"></i>`).join("")}</div>`;
}

function renderOrgTable(data) {
  const body = document.querySelector("#org-table tbody");
  body.innerHTML = data.orgs.map((org) => `
    <tr class="rank-${org.rank}">
      <td class="num">${org.rank}</td>
      <td>${escapeHtml(org.name)}</td>
      <td class="num">${fmt(org.user_count)}${org.active_users ? `<span style="color:#93a2b0"> (稼働 ${org.active_users})</span>` : ""}</td>
      <td class="num">${fmt(org.acus)}</td>
      <td class="num">${fmt(org.acus_per_user)}</td>
      <td class="num">${fmt(org.sessions)}</td>
      <td class="num">${fmt(org.prs_created)}</td>
      <td class="num">${fmt(org.prs_merged)}</td>
      <td class="num">${org.merge_rate === null ? "-" : fmt(org.merge_rate, "%")}</td>
      <td>${sparkline(org.hourly_acus)}</td>
      <td class="num">${relativeLabel(org.last_activity)}</td>
    </tr>`).join("");
}

function renderHeatmap(data) {
  const orgs = data.heatmap.orgs;
  if (!orgs.length) {
    document.getElementById("heatmap").innerHTML = '<div class="sub">データなし</div>';
    return;
  }
  const max = Math.max(...orgs.flatMap((org) => org.values), 0.0001);
  const head = `<tr><th></th>${data.hours.map((h) => `<th class="hm-head">${hourLabel(h).split(" ")[1].replace("時", "")}</th>`).join("")}</tr>`;
  const rows = orgs.map((org) => `<tr><td class="hm-label">${escapeHtml(org.name)}</td>${org.values.map((v) => {
    const intensity = v / max;
    const color = v === 0 ? "#1c2731" : `rgba(230,214,174,${0.12 + intensity * 0.88})`;
    return `<td><div class="hm-cell" style="background:${color}" title="${fmt(v)} ACU"></div></td>`;
  }).join("")}</tr>`).join("");
  document.getElementById("heatmap").innerHTML = `<table>${head}${rows}</table>`;
}

function renderIdleOrgs(data) {
  const element = document.getElementById("idle-orgs");
  if (!data.idle_orgs.length) {
    element.innerHTML = '<span class="chip ok">全 Org がセッション実行済み</span>';
    return;
  }
  element.innerHTML = data.idle_orgs
    .map((org) => `<span class="chip">${escapeHtml(org.name)}（${org.user_count}名・0セッション）</span>`)
    .join("");
}

function renderSessionFeed(elementId, sessions) {
  document.getElementById(elementId).innerHTML = sessions.map((session) => `
    <div class="feed-item">
      <a href="${session.url}" target="_blank" rel="noreferrer">
        <span class="dot ${session.status}"></span>${escapeHtml(session.title || "(無題)")}
      </a>
      <div class="feed-meta">
        <span>${escapeHtml(session.org_name)}</span>
        <span>${fmt(session.acus)} ACU</span>
        <span>${escapeHtml(session.status_detail || session.status || "")}</span>
        <span>${session.prs_merged ? `マージ ${session.prs_merged}` : ""}</span>
        <span>${relativeLabel(session.updated_at)}</span>
      </div>
    </div>`).join("");
}

function renderFeed(data) {
  renderSessionFeed("feed", data.recent_sessions);
  renderSessionFeed("top-feed", data.top_sessions);
}

function escapeHtml(value) {
  return String(value === null || value === undefined ? "" : value)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function renderHeader(data) {
  const hours = data.hours;
  document.getElementById("window-label").textContent =
    hours.length ? `集計期間: ${hourLabel(hours[0])} 〜 ${hourLabel(hours[hours.length - 1])}（JST・1時間バケット）` : "データなし";
  document.getElementById("countdown").textContent = data.hackathon.remaining_seconds === null
    ? "—" : durationLabel(data.hackathon.remaining_seconds);
  document.getElementById("updated").textContent = clockLabel(data.generated_at);
  const collector = data.collector;
  document.getElementById("footer").innerHTML = collector.last_error
    ? `<div class="error-banner">収集エラー: ${escapeHtml(collector.last_error)}</div>`
    : `<span class="brand-note">AIAU Hackathon</span> ・ 収集間隔 ${collector.poll_interval}s ・ 最終収集 ${collector.last_poll_at ? clockLabel(collector.last_poll_at) : "-"} ・ 画面更新 ${REFRESH_MS / 1000}s`;
}

function render(data) {
  renderHeader(data);
  renderKpis(data);
  renderMainCharts(data);
  renderDonuts(data);
  renderOrgTable(data);
  renderHeatmap(data);
  renderIdleOrgs(data);
  renderFeed(data);
}

async function refresh() {
  try {
    const response = await fetch("/api/data", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    render(await response.json());
  } catch (error) {
    if (window.EMBEDDED_DATA) {
      render(window.EMBEDDED_DATA);
      document.getElementById("footer").innerHTML =
        `<span class="brand-note">AIAU Hackathon</span> ・ 静的スナップショット（サーバー未接続）`;
      return;
    }
    document.getElementById("footer").innerHTML =
      `<div class="error-banner">ダッシュボード更新失敗: ${escapeHtml(error.message)}</div>`;
  }
}

refresh();
setInterval(refresh, REFRESH_MS);
