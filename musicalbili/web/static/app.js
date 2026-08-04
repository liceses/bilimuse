// MusicalBILI Web 前端（原生 JS）
"use strict";

const $ = (sel) => document.querySelector(sel);

async function loadDoctor() {
  try {
    const r = await fetch("/api/doctor");
    const d = await r.json();
    const whisper = d.whisper;
    const models = d.models.map((m) => `${m.name}(${m.size_mb}MB)`).join(", ") || "无";
    $("#doctor").textContent =
      `Python ${d.python} | 登录:${d.logged_in ? "是" : "否"} | lyric-align:${d.lyric_align ? "✓" : "✗"} ` +
      `| whisper 模型: ${whisper.used || "(未配置)"}(${whisper.note}) | 已检测: ${models}`;
  } catch (e) {
    $("#doctor").textContent = "doctor 加载失败";
  }
}

function status(text) {
  $("#status").textContent = text;
}

function progress(pct) {
  const bar = $("#progress");
  bar.style.width = `${pct}%`;
}

function log(line) {
  const el = $("#log");
  el.textContent += line + "\n";
  el.scrollTop = el.scrollHeight;
}

function fmtPlay(n) {
  return n >= 10000 ? (n / 10000).toFixed(1) + "万" : String(n);
}

async function doSearch(query) {
  const tbody = $("#results tbody");
  tbody.innerHTML = "";
  status(`搜索: ${query} ...`);
  const r = await fetch(`/api/search?q=${encodeURIComponent(query)}`);
  const hits = await r.json();
  if (!hits.length) {
    status("无结果");
    return;
  }
  for (const h of hits) {
    const v = h.version;
    const tr = document.createElement("tr");
    tr.dataset.bvid = v.bvid;
    tr.innerHTML =
      `<td>${h.source === "lyric" ? "歌词反查" : "直接"}</td>` +
      `<td>${v.bvid}</td><td>${v.duration}s</td><td>${fmtPlay(v.play)}</td>` +
      `<td>${escapeHtml(v.author)}</td><td>${escapeHtml(v.title)}</td>`;
    tr.addEventListener("click", () => download(v.bvid, v.title));
    tbody.appendChild(tr);
  }
  status(`${hits.length} 条，点击行开始下载`);
}

function escapeHtml(s) {
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}

function download(bvid, title) {
  if (!$("#progress").style.display) {
    $("#progress").style.display = "block";
  }
  status(`下载: ${title}`);
  log(`>> 开始下载 ${bvid}`);
  const ws = new WebSocket(`ws://${location.host}/ws/download`);
  ws.onopen = () => ws.send(JSON.stringify({ bvid, page: 1 }));
  ws.onmessage = (e) => {
    const ev = JSON.parse(e.data);
    switch (ev.type) {
      case "info":
        status(`标题: ${ev.title} | UP主: ${ev.author}`);
        break;
      case "stage":
        status(ev.text || ev.stage);
        if (ev.stage === "download") progress(0);
        break;
      case "progress":
        progress(ev.pct);
        break;
      case "message":
        status(ev.text);
        break;
      case "meta":
        status(`匹配: ${ev.meta.source} → ${ev.meta.artist_str} - ${ev.meta.name}`);
        log(`标签: ${ev.meta.artist_str} - ${ev.meta.name}`);
        break;
      case "lyric":
        status(`歌词: ${ev.lyric.source}（${ev.lyric.calib_method}）`);
        log(`歌词: ${ev.lyric.source}（${ev.lyric.calib_method}）`);
        break;
      case "warning":
        log(`警告: ${ev.text}`);
        break;
      case "result":
        log(`完成: ${ev.result.path}`);
        status("完成");
        ws.close();
        break;
      case "error":
        log(`失败: ${ev.message}`);
        status(`失败: ${ev.message}`);
        ws.close();
        break;
    }
  };
}

$("#search-form").addEventListener("submit", (e) => {
  e.preventDefault();
  doSearch($("#q").value.trim());
});

loadDoctor();
