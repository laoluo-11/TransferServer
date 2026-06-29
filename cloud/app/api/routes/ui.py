from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["ui"])


PANEL_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Bumi Local Task Panel</title>
  <style>
    :root {
      --bg: #f5f1e8;
      --ink: #17202a;
      --panel: #fffdf8;
      --line: #d7ceb9;
      --accent: #0b6e4f;
      --accent-2: #db6c22;
      --muted: #66727f;
      --danger: #b42318;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Segoe UI", "PingFang SC", sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top right, rgba(11,110,79,0.16), transparent 25%),
        radial-gradient(circle at bottom left, rgba(219,108,34,0.15), transparent 25%),
        var(--bg);
    }
    .shell {
      max-width: 1380px;
      margin: 0 auto;
      padding: 24px;
    }
    .hero {
      display: grid;
      grid-template-columns: 1.5fr 1fr;
      gap: 16px;
      margin-bottom: 18px;
    }
    .card {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 18px;
      box-shadow: 0 12px 35px rgba(23,32,42,0.06);
    }
    .hero h1 {
      margin: 0 0 8px;
      font-size: 32px;
      line-height: 1.1;
    }
    .muted { color: var(--muted); }
    .quick-links {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      margin-top: 12px;
    }
    .quick-links a, button {
      border: none;
      border-radius: 999px;
      padding: 10px 14px;
      cursor: pointer;
      background: var(--accent);
      color: white;
      text-decoration: none;
      font-size: 14px;
    }
    button.secondary, .quick-links a.secondary {
      background: #ece5d4;
      color: var(--ink);
    }
    button.warn {
      background: var(--danger);
    }
    .grid {
      display: grid;
      grid-template-columns: 1.1fr 1.2fr;
      gap: 16px;
    }
    .stack {
      display: grid;
      gap: 16px;
    }
    label {
      display: block;
      font-size: 13px;
      margin-bottom: 6px;
      color: var(--muted);
    }
    input, select, textarea {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 10px 12px;
      background: white;
      font: inherit;
    }
    textarea { min-height: 120px; resize: vertical; }
    .row {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
    }
    .toolbar {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      margin-top: 12px;
    }
    .kv {
      display: grid;
      grid-template-columns: 140px 1fr;
      gap: 8px;
      font-size: 14px;
    }
    .kv div { padding: 6px 0; border-bottom: 1px dashed var(--line); }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }
    th, td {
      text-align: left;
      padding: 10px 8px;
      border-bottom: 1px solid #ede5d4;
      vertical-align: top;
    }
    th { color: var(--muted); font-weight: 600; }
    .status {
      display: inline-block;
      padding: 4px 8px;
      border-radius: 999px;
      font-size: 12px;
      background: #e7f5ef;
      color: var(--accent);
    }
    .status.warn { background: #fff2e8; color: var(--accent-2); }
    .status.err { background: #fdecec; color: var(--danger); }
    pre {
      margin: 0;
      white-space: pre-wrap;
      word-break: break-word;
      font-size: 12px;
    }
    #resultBox {
      min-height: 64px;
      padding: 12px;
      border-radius: 12px;
      background: #f7f4ed;
      border: 1px solid var(--line);
      font-size: 13px;
    }
    @media (max-width: 980px) {
      .hero, .grid, .row {
        grid-template-columns: 1fr;
      }
    }
  </style>
</head>
<body>
  <div class="shell">
    <section class="hero">
      <div class="card">
        <h1>Bumi Local Task Panel</h1>
        <div class="muted">本地调试面板，用来下发技能任务、查看机器人状态、最近任务和告警。适合单机器人联调和演示排障。</div>
        <div class="quick-links">
          <a href="/docs" target="_blank">Swagger Docs</a>
          <a href="/openapi.json" class="secondary" target="_blank">OpenAPI JSON</a>
          <button class="secondary" onclick="refreshAll()">立即刷新</button>
        </div>
      </div>
      <div class="card">
        <div class="kv">
          <div>面板模式</div><div>单机器人 / 本地联调</div>
          <div>默认任务接口</div><div><code>POST /api/v1/robots/{robot_id}/tasks</code></div>
          <div>推荐联调顺序</div><div>先连 Agent，再发 speak，然后 move，再测 interrupt。</div>
        </div>
      </div>
    </section>

    <section class="grid">
      <div class="stack">
        <div class="card">
          <h2>任务下发</h2>
          <div class="row">
            <div>
              <label for="robotId">Robot ID</label>
              <input id="robotId" value="bumi_001" />
            </div>
            <div>
              <label for="skill">Skill</label>
              <select id="skill" onchange="fillSkillTemplate()">
                <option value="speak">speak</option>
                <option value="move">move</option>
                <option value="gesture">gesture</option>
                <option value="play_teach">play_teach</option>
                <option value="stop">stop</option>
              </select>
            </div>
          </div>
          <div class="row">
            <div>
              <label for="timeoutMs">timeout_ms</label>
              <input id="timeoutMs" type="number" value="5000" />
            </div>
            <div>
              <label for="priority">priority</label>
              <input id="priority" type="number" value="50" />
            </div>
          </div>
          <div style="margin-top: 12px;">
            <label for="params">Params JSON</label>
            <textarea id="params">{ "text": "你好，我是 Bumi。" }</textarea>
          </div>
          <div class="toolbar">
            <button onclick="submitTask()">发送任务</button>
            <button class="secondary" onclick="fillSkillTemplate()">填充模板</button>
            <button class="warn" onclick="interruptTask()">中断当前任务</button>
          </div>
          <div style="margin-top: 14px;">
            <label>结果</label>
            <div id="resultBox">等待操作...</div>
          </div>
        </div>

        <div class="card">
          <h2>当前机器人状态</h2>
          <div class="kv" id="stateBox">
            <div>robot_id</div><div>-</div>
            <div>online</div><div>-</div>
            <div>battery</div><div>-</div>
            <div>workmode</div><div>-</div>
            <div>motion_state</div><div>-</div>
            <div>speech_state</div><div>-</div>
            <div>safety_state</div><div>-</div>
            <div>current_task</div><div>-</div>
          </div>
        </div>
      </div>

      <div class="stack">
        <div class="card">
          <h2>机器人列表</h2>
          <table>
            <thead>
              <tr>
                <th>Robot</th>
                <th>Online</th>
                <th>Battery</th>
                <th>Safety</th>
                <th>Current Task</th>
              </tr>
            </thead>
            <tbody id="robotsTable"></tbody>
          </table>
        </div>

        <div class="card">
          <h2>最近任务</h2>
          <table>
            <thead>
              <tr>
                <th>Task</th>
                <th>Skill</th>
                <th>Status</th>
                <th>Result</th>
              </tr>
            </thead>
            <tbody id="tasksTable"></tbody>
          </table>
        </div>

        <div class="card">
          <h2>最近告警</h2>
          <table>
            <thead>
              <tr>
                <th>Time</th>
                <th>Robot</th>
                <th>Code</th>
                <th>Message</th>
              </tr>
            </thead>
            <tbody id="alertsTable"></tbody>
          </table>
        </div>
      </div>
    </section>
  </div>

  <script>
    const templates = {
      speak: { text: "你好，我是 Bumi。", voice: "default" },
      move: { x: 0.15, yaw: 0.10, duration_ms: 1200 },
      gesture: { name: "wave_hand" },
      play_teach: { index: 1 },
      stop: {}
    };

    function setResult(value) {
      document.getElementById("resultBox").textContent =
        typeof value === "string" ? value : JSON.stringify(value, null, 2);
    }

    function fillSkillTemplate() {
      const skill = document.getElementById("skill").value;
      document.getElementById("params").value = JSON.stringify(templates[skill], null, 2);
      if (skill === "move") {
        document.getElementById("timeoutMs").value = 3000;
      } else if (skill === "play_teach") {
        document.getElementById("timeoutMs").value = 15000;
      } else {
        document.getElementById("timeoutMs").value = 5000;
      }
    }

    async function fetchJson(url, options) {
      const res = await fetch(url, options);
      const data = await res.json();
      if (!res.ok) {
        throw new Error(JSON.stringify(data));
      }
      return data;
    }

    async function submitTask() {
      try {
        const robotId = document.getElementById("robotId").value.trim();
        const skill = document.getElementById("skill").value;
        const params = JSON.parse(document.getElementById("params").value || "{}");
        const timeoutMs = Number(document.getElementById("timeoutMs").value || "5000");
        const priority = Number(document.getElementById("priority").value || "50");
        const body = {
          skill,
          params,
          policy: {
            interruptible: true,
            timeout_ms: timeoutMs,
            priority,
            need_ack: true,
            on_error: "abort"
          },
          source: {
            type: "panel",
            name: "local_debug_panel"
          }
        };
        const data = await fetchJson(`/api/v1/robots/${robotId}/tasks`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body)
        });
        setResult(data);
        await refreshAll();
      } catch (error) {
        setResult(String(error));
      }
    }

    async function interruptTask() {
      try {
        const robotId = document.getElementById("robotId").value.trim();
        const data = await fetchJson(`/api/v1/robots/${robotId}/interrupt`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ reason: "panel_interrupt", scope: "current_task" })
        });
        setResult(data);
        await refreshAll();
      } catch (error) {
        setResult(String(error));
      }
    }

    function renderState(state) {
      const entries = [
        ["robot_id", state.robot_id],
        ["online", state.online],
        ["battery", state.battery_percent],
        ["workmode", state.workmode],
        ["motion_state", state.motion_state],
        ["speech_state", state.speech_state],
        ["safety_state", state.safety_state],
        ["current_task", state.current_task_id || "-"]
      ];
      document.getElementById("stateBox").innerHTML = entries
        .map(([k, v]) => `<div>${k}</div><div>${v}</div>`)
        .join("");
    }

    function renderRobots(items) {
      document.getElementById("robotsTable").innerHTML = items.map((item) => `
        <tr onclick="selectRobot('${item.robot_id}')" style="cursor:pointer;">
          <td>${item.robot_id}</td>
          <td><span class="status ${item.online ? "" : "err"}">${item.online}</span></td>
          <td>${item.battery_percent}</td>
          <td><span class="status ${item.safety_state === "normal" ? "" : "warn"}">${item.safety_state}</span></td>
          <td>${item.current_task_id || "-"}</td>
        </tr>
      `).join("") || `<tr><td colspan="5" class="muted">暂无机器人数据</td></tr>`;
    }

    function renderTasks(items) {
      document.getElementById("tasksTable").innerHTML = items.map((task) => `
        <tr>
          <td><code>${task.task_id}</code></td>
          <td>${task.skill}</td>
          <td><span class="status ${task.status === "failed" ? "err" : task.status === "queued" ? "warn" : ""}">${task.status}</span></td>
          <td><pre>${task.result_message || "-"}</pre></td>
        </tr>
      `).join("") || `<tr><td colspan="4" class="muted">暂无任务</td></tr>`;
    }

    function renderAlerts(items) {
      document.getElementById("alertsTable").innerHTML = items.map((alert) => `
        <tr>
          <td>${new Date(alert.timestamp).toLocaleTimeString()}</td>
          <td>${alert.robot_id}</td>
          <td>${alert.code}</td>
          <td><pre>${alert.message}</pre></td>
        </tr>
      `).join("") || `<tr><td colspan="4" class="muted">暂无告警</td></tr>`;
    }

    async function refreshAll() {
      try {
        const robotId = document.getElementById("robotId").value.trim();
        const [robots, tasks, alerts, state] = await Promise.all([
          fetchJson("/api/v1/robots"),
          fetchJson("/api/v1/tasks?limit=20"),
          fetchJson("/api/v1/alerts?limit=20"),
          fetchJson(`/api/v1/robots/${robotId}/state`)
        ]);
        renderRobots(robots.data);
        renderTasks(tasks.data);
        renderAlerts(alerts.data);
        renderState(state.data);
      } catch (error) {
        setResult(String(error));
      }
    }

    function selectRobot(robotId) {
      document.getElementById("robotId").value = robotId;
      refreshAll();
    }

    fillSkillTemplate();
    refreshAll();
    setInterval(refreshAll, 3000);
  </script>
</body>
</html>
"""


@router.get(
    "/panel",
    response_class=HTMLResponse,
    summary="Local task panel",
    description="Browser-based local debug panel for single-robot task testing.",
)
async def panel() -> HTMLResponse:
    return HTMLResponse(PANEL_HTML)
