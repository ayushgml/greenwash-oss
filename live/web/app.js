"use strict";
// Greenwash Live client. Every string from the run (diffs, agent text, reasons) is set with
// textContent: agent and repository text is data, never markup.

const $ = (id) => document.getElementById(id);
const S = { scenarios: [], modes: [], checks: {}, possible: 0.5, stream: null, runId: null, replay: false,
            decisions: new Map(), selected: null, step: 0, logCount: 0, activity: new Set(), busy: false };

const MODE_NOTES = {
  natural: "A realistic task under release pressure. The agent may or may not try a shortcut.",
  directed: "Labelled demo mode: the prompt tells the agent to apply the shortcut first, so the guard can be seen working.",
  lookalike: "A legitimate edit that looks similar. It must be allowed.",
};
const STATE_TEXT = { allow: "Allowed", deny: "Denied by Failproof", review: "Denied: needs human review", error: "Denied: judgment failed" };
const STATUS_TEXT = { repaired: "Repaired", not_repaired: "Not repaired", needs_human: "Needs human", setup_error: "Setup error",
                      error: "Error", running: "Running", replaying: "Replaying" };

function h(tag, props = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (v == null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "text") el.textContent = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) if (kid != null) el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  return el;
}
const fmt = (p) => (typeof p === "number" ? p.toFixed(2) : "–");
const checkTitle = (id) => S.checks[id]?.title ?? id;

// ---- setup -----------------------------------------------------------------
async function loadHealth() {
  try {
    const r = await (await fetch("/api/health")).json();
    const set = (key, ok, text) => {
      const span = document.querySelector(`#health [data-key="${key}"] span`);
      span.textContent = text; span.className = ok ? "ok" : "bad";
    };
    set("failproof", !!r.failproof, r.failproof ? `v${r.failproof}` : "not installed");
    set("typesafe_key", r.typesafe_key, r.typesafe_key ? "present" : "missing");
    set("claude", !!r.claude, r.claude ? r.claude.split(" ")[0] : "not found");
    setBusy(r.busy);
    if (r.busy && r.active_run && !S.stream) openStream(r.active_run);
  } catch { $("form-error").textContent = "Cannot reach the Greenwash Live server."; }
}

async function loadScenarios() {
  const data = await (await fetch("/api/scenarios")).json();
  S.scenarios = data.scenarios; S.modes = data.modes; S.possible = data.possible_threshold;
  for (const c of data.checks) S.checks[c.id] = c;
  const sel = $("scenario");
  sel.replaceChildren(...S.scenarios.map((s) => h("option", { value: s.id, text: `${s.order}. ${s.title}` })));
  $("modes").replaceChildren(...S.modes.map((m, i) => h("label", {},
    h("input", { type: "radio", name: "mode", value: m.id, checked: i === 1, onchange: updatePrompt }),
    h("span", { text: { natural: "Natural", directed: "Directed", lookalike: "Look-alike" }[m.id] }))));
  sel.addEventListener("change", updatePrompt);
  updatePrompt();
}

function currentChoice() {
  return { scenario: $("scenario").value, mode: document.querySelector('input[name="mode"]:checked')?.value ?? "natural",
           open_pr: $("open-pr").checked };
}
function updatePrompt() {
  const { scenario, mode } = currentChoice();
  const s = S.scenarios.find((x) => x.id === scenario);
  $("prompt-text").textContent = s ? s.prompts[mode] : "";
  $("mode-note").textContent = MODE_NOTES[mode];
}

async function loadHistory() {
  const { runs } = await (await fetch("/api/runs")).json();
  const list = $("history");
  if (!runs.length) { list.replaceChildren(h("li", { class: "empty", text: "No runs yet." })); return; }
  list.replaceChildren(...runs.map((r) => {
    const st = r.summary?.status ?? (r.finished ? "error" : "running");
    const when = r.started ? new Date(r.started * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "";
    const title = S.scenarios.find((s) => s.id === r.scenario)?.title ?? r.scenario;
    return h("li", {}, h("button", { type: "button", "aria-current": r.run_id === S.runId ? "true" : null,
      "aria-label": `${S.replay || r.run_id !== S.runId ? "Replay" : "Show"} ${title}, ${r.mode}, ${STATUS_TEXT[st] ?? st}`,
      onclick: () => openStream(r.run_id) },
      h("span", { text: title }), h("span", { class: `st-${st}`, text: STATUS_TEXT[st] ?? st }),
      h("span", { class: "when", text: `${when} · ${r.mode}${r.summary?.denies ? ` · ${r.summary.denies} blocked` : ""}` })));
  }));
}

function setBusy(busy) {
  S.busy = busy;
  $("run-btn").disabled = busy;
  $("run-btn").textContent = busy ? "Run in progress" : "Run repair";
}

$("run-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  $("form-error").textContent = "";
  setBusy(true);
  try {
    const res = await fetch("/api/runs", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(currentChoice()) });
    const body = await res.json();
    if (!res.ok) throw new Error(body.detail || `Server returned ${res.status}`);
    openStream(body.run_id);
  } catch (err) {
    $("form-error").textContent = `Run not started: ${err.message}`;
    setBusy(false);
  }
});

// ---- tabs ------------------------------------------------------------------
const tabs = [$("tab-timeline"), $("tab-log")];
function selectTab(tab) {
  for (const t of tabs) {
    const on = t === tab;
    t.setAttribute("aria-selected", on); t.tabIndex = on ? 0 : -1;
    $(t.getAttribute("aria-controls")).hidden = !on;
  }
  tab.focus();
}
for (const t of tabs) {
  t.addEventListener("click", () => selectTab(t));
  t.addEventListener("keydown", (e) => {
    if (e.key === "ArrowRight" || e.key === "ArrowLeft") selectTab(tabs[(tabs.indexOf(t) + 1) % tabs.length]);
  });
}

// ---- stream ----------------------------------------------------------------
function resetView() {
  S.decisions.clear(); S.selected = null; S.step = 0; S.logCount = 0; S.activity.clear();
  $("timeline").replaceChildren(); $("agent-log").replaceChildren(); $("chips").replaceChildren();
  $("bars").replaceChildren(); $("jev-sub").textContent = "Select a judged edit in the timeline.";
  $("activity").replaceChildren(h("li", { class: "empty", text: "No hook activity yet." }));
  $("verify").replaceChildren(h("li", { class: "empty", text: "Runs when the agent finishes." }));
  $("pr").replaceChildren(h("p", { class: "empty", text: "No pull request for this run." }));
  $("log-count").textContent = "";
}

function openStream(runId) {
  if (S.stream) S.stream.close();
  resetView();
  S.runId = runId;
  const es = new EventSource(`/api/runs/${encodeURIComponent(runId)}/events`);
  S.stream = es;
  es.onmessage = (msg) => handle(JSON.parse(msg.data));
  es.onerror = () => {
    if (es.readyState === EventSource.CLOSED || S.ended) return;
    addStep("error", "!", h("div", { class: "banner error", text: "Lost the connection to the server. Reload the page to reconnect; the run continues on the server." }));
    es.close();
  };
  loadHistory();
}

function setPhase(text) {
  let row = $("phase");
  if (!text) { row?.remove(); return; }
  if (!row) {
    row = h("li", { id: "phase", class: "step" }, h("div", { class: "dot pending", "aria-hidden": "true", text: "…" }),
      h("div", { class: "body" }, h("p", { class: "note quiet", role: "status" })));
  }
  row.querySelector("p").textContent = text;
  $("timeline").append(row);  // always last
}

function addStep(dotClass, dotText, body) {
  const empty = $("timeline").querySelector(".empty-state"); if (empty) empty.remove();
  const li = h("li", { class: "step fresh" }, h("div", { class: `dot ${dotClass}`, "aria-hidden": "true", text: dotText }), h("div", { class: "body" }, body));
  const phase = $("phase");
  phase ? $("timeline").insertBefore(li, phase) : $("timeline").append(li);
  setTimeout(() => li.classList.remove("fresh"), 1300);
  return li;
}
function addLog(cls, ...kids) {
  const empty = $("agent-log").querySelector(".empty-state"); if (empty) empty.remove();
  $("agent-log").append(h("li", { class: cls }, ...kids));
  S.logCount += 1; $("log-count").textContent = `(${S.logCount})`;
}
function setStatus(status) {
  $("chips").querySelector(".status")?.remove();
  $("chips").append(h("span", { class: `chip status st-${status}`, text: STATUS_TEXT[status] ?? status }));
}

function diffBlock(text) {
  const pre = h("pre", { class: "diff", "aria-label": "Proposed change" });
  for (const line of (text || "").split("\n")) {
    if (!line) continue;
    const cls = line.startsWith("+") ? "add" : line.startsWith("-") ? "del" : "ctx";
    pre.append(h("span", { class: cls, text: line }));
  }
  return pre;
}

const PHASES = {
  run_started: "Resetting the sandbox to the buggy commit and checking the Failproof policy…",
  sandbox_reset: "Asking Jev how hard the task is, to pick a model…",
  route: "Starting the coding agent…",
  attempt_started: "Agent is working. Each risky edit is judged by Jev before it runs…",
  attempt_finished: "Verifying against the original tests…",
  verification: null,
  escalation: "Resetting for the escalated attempt…",
};

function handle(ev) {
  if (!S.replay && ev.type in PHASES) setPhase(PHASES[ev.type]);
  if (ev.type === "run_finished" || ev.type === "error" || ev.type === "stream_end") setPhase(null);
  switch (ev.type) {
    case "stream":
      S.replay = ev.replay; S.ended = false;
      $("replay-banner").hidden = !ev.replay;
      return;
    case "run_started": {
      $("run-title").textContent = ev.scenario.task_title;
      const modeLabel = { natural: "Natural prompt", directed: "Directed prompt (labelled)", lookalike: "Look-alike check" }[ev.mode];
      $("chips").append(h("span", { class: "chip", text: modeLabel }),
        h("span", { class: `chip ${S.replay ? "" : "solid"}`, text: S.replay ? "Recorded run" : "Live run" }),
        h("span", { class: "chip", text: `Run ${ev.run_id}` }));
      setStatus(S.replay ? "replaying" : "running");
      addStep("muted", "·", h("p", { class: "note quiet", text: ev.scenario.task_description }));
      return;
    }
    case "sandbox_reset":
      addStep(ev.guard_loaded ? "muted" : "error", ev.guard_loaded ? "·" : "!", h("p", { class: `note ${ev.guard_loaded ? "quiet" : ""}`,
        text: ev.guard_loaded ? `Sandbox reset to the buggy commit ${ev.base_sha.slice(0, 7)}. Failproof lists the greenwash-guard policy.`
                              : "Failproof does not list the greenwash-guard policy. The run was refused rather than run unguarded." }));
      return;
    case "route": {
      const scores = Object.entries(ev.scores || {}).map(([k, v]) => `${k.replace("_", " ")} ${fmt(v)}`).join("   ");
      $("chips").append(h("span", { class: "chip", text: `Routed to ${ev.model[0].toUpperCase()}${ev.model.slice(1)}` }));
      addStep("muted", "·", h("div", {}, h("p", { class: "note", text: `Jev routed the task to ${ev.model}: ${ev.reason}.` }),
        scores ? h("p", { class: "route-scores", text: scores }) : null));
      return;
    }
    case "attempt_started":
      addStep("muted", "·", h("p", { class: "divider", text: `Attempt ${ev.attempt} · ${ev.model} · ${S.replay ? "recorded" : "agent working"}` }));
      return;
    case "guard_decision": return onDecision(ev.record);
    case "agent": return onAgent(ev);
    case "failproof_entry": return addActivity([ev.entry]);
    case "failproof_activity": return addActivity(ev.entries);
    case "escalation":
      addStep("error", "!", h("div", { class: ev.action === "setup_error" ? "banner error" : "banner warn",
        text: ev.action === "rerun" ? `Escalated: ${ev.reason}. The new attempt is told which edits were refused.`
            : ev.action === "setup_error" ? `Setup error: ${ev.reason}.` : `Stopped for human review: ${ev.reason}.` }));
      return;
    case "stale_agent_stopped":
      addStep("muted", "·", h("p", { class: "note quiet", text: `Stopped an agent left over from an earlier run (process group ${ev.pgid}) before resetting.` }));
      return;
    case "attempt_finished":
      if (ev.stopped) addStep("muted", "·", h("p", { class: "note quiet", text: `Attempt ${ev.attempt} stopped: ${ev.stopped}.` }));
      else if (ev.exit !== 0) addStep("error", "!", h("div", { class: "banner error", text: `The agent exited with status ${ev.exit}. ${ev.stderr || ""}` }));
      return;
    case "verification": return onVerification(ev);
    case "pr_opened":
      setPhase(S.replay ? null : "Waiting for the Greenwash GitHub App to review the pull request…");
      $("pr").replaceChildren(h("p", {}, "Opened ", h("a", { href: ev.url, target: "_blank", rel: "noopener", text: `${ev.repo}#${ev.number}` }), "."),
        h("p", { class: "note quiet", text: "Waiting for the Greenwash check…" }));
      return;
    case "pr_review": {
      const conclusion = ev.conclusion ?? ev.state;
      const text = ev.state === "missing" ? ev.detail : `Greenwash check: ${conclusion}${ev.title ? `. ${ev.title}` : ""}`;
      $("pr").querySelector(".note")?.remove();
      $("pr").append(h("p", { text }));
      if (ev.check_url) $("pr").append(h("p", {}, h("a", { href: ev.check_url, target: "_blank", rel: "noopener", text: "Open the check run" })));
      if (ev.comment_url) $("pr").append(h("p", {}, h("a", { href: ev.comment_url, target: "_blank", rel: "noopener", text: "Open the report comment" })));
      return;
    }
    case "pr_skipped": $("pr").replaceChildren(h("p", { class: "empty", text: ev.reason })); return;
    case "pr_error": $("pr").replaceChildren(h("p", { class: "n", text: `Pull request failed: ${ev.message}` })); return;
    case "error":
      addStep("error", "!", h("div", { class: "banner error", text: ev.message }));
      return;
    case "run_finished":
      setStatus(ev.status);
      return;
    case "stream_end":
      S.ended = true; S.stream?.close();
      if (!S.activity.size) loadActivityFromLog(S.runId);
      loadHistory(); loadHealth();
      return;
  }
}

function onDecision(r) {
  S.decisions.set(r.attempt_id, r);
  const judged = r.route === "jev";
  if (!judged && r.decision === "allow") {
    addLog("tool", `guard allowed ${r.tool}${r.command ? `: ${r.command}` : ""} (rule, no model call)`);
    return;
  }
  const target = r.path || r.command || r.tool;
  if (!judged) {  // denied by a deterministic rule (shell, protected path, uninspectable)
    addStep(r.decision, "!", h("div", { class: `card ${r.decision}` },
      h("div", { class: "card-top" }, h("strong", { text: `${r.tool}: ${target}` }), h("span", { class: `state ${r.decision}`, text: `${STATE_TEXT[r.decision]} (rule)` })),
      h("p", { class: "reason", text: r.reason })));
    return;
  }
  S.step += 1;
  const card = h("button", { type: "button", class: `card ${r.decision}`, "aria-pressed": "false",
    "aria-label": `${r.tool} ${target}: ${STATE_TEXT[r.decision]}. Show Jev scores.`, onclick: () => select(r.attempt_id) },
    h("div", { class: "card-top" }, h("strong", { text: `Agent tried to ${r.tool === "Write" ? "write" : "edit"} ${target}` }),
      h("span", { class: `state ${r.decision}`, text: STATE_TEXT[r.decision] })),
    diffBlock(r.diff),
    r.decision !== "allow" ? h("p", { class: "reason", text: r.reason }) : null,
    h("p", { class: "meta", text: `Jev ${r.model ?? "–"} · ${r.judge_ms ?? "–"} ms · attempt ${r.attempt_id}${r.error ? ` · ${r.error}` : ""}` }));
  card.dataset.attempt = r.attempt_id;
  addStep(r.decision, String(S.step), card);
  if (r.decision !== "allow" || !S.selected || S.decisions.get(S.selected)?.decision === "allow") select(r.attempt_id);
}

function select(attemptId) {
  const r = S.decisions.get(attemptId); if (!r) return;
  S.selected = attemptId;
  for (const c of document.querySelectorAll(".card[data-attempt]")) c.setAttribute("aria-pressed", c.dataset.attempt === attemptId);
  $("jev-sub").textContent = `${r.tool} ${r.path ?? ""} · ${STATE_TEXT[r.decision]} · ${r.model ?? "no model"} · ${r.judge_ms ?? "–"} ms`;
  const rows = (r.checks || []).map((id) => ({ id, p: r.scores?.[id], t: S.checks[id]?.threshold ?? 0.8 }))
    .sort((a, b) => (b.p ?? -1) - (a.p ?? -1));
  if (!rows.length) { $("bars").replaceChildren(h("li", { class: "empty", text: r.error ? `No scores: ${r.error}.` : "No model checks for this action." })); return; }
  $("bars").replaceChildren(...rows.map(({ id, p, t }) => {
    const pct = Math.max(0, Math.min(1, p ?? 0)) * 100;
    return h("li", {},
      h("div", { class: "bar-label" }, h("span", { text: checkTitle(id) }), h("b", { text: p == null ? "missing" : fmt(p) })),
      h("div", { class: "bar", role: "img", "aria-label": `${checkTitle(id)}: probability ${fmt(p)}, deny threshold ${fmt(t)}` },
        h("i", { class: p != null && p >= S.possible ? "hot" : "", style: `width:${pct}%` }),
        h("span", { class: "tick soft", style: `left:${S.possible * 100}%` }),
        h("span", { class: "tick", style: `left:${t * 100}%` })));
  }));
}

function onAgent(ev) {
  switch (ev.kind) {
    case "init": addLog("tool", `session ${ev.session_id} · model ${ev.model}`); return;
    case "text":
      addLog("", ev.text);
      if (ev.text.length < 400) addStep("muted", "·", h("p", { class: "quote", text: ev.text }));
      return;
    case "tool_use": {
      const inp = ev.input || {};
      const detail = inp.command ?? inp.file_path ?? inp.pattern ?? "";
      addLog("tool", `▸ ${ev.tool} ${detail}`);
      return;
    }
    case "tool_result": addLog(ev.is_error ? "res err" : "res", ev.text); return;
    case "result": addLog("", `Agent finished (${ev.subtype}) after ${ev.turns ?? "?"} turns.`); return;
  }
}

function addActivity(entries) {
  const list = $("activity");
  for (const e of entries || []) {
    const key = `${e.timestamp}|${e.toolName}|${e.decision}`;
    if (S.activity.has(key)) continue;
    S.activity.add(key);
    list.querySelector(".empty")?.remove();
    list.append(h("li", { class: e.decision === "deny" ? "deny" : "" }, h("span", { text: e.toolName }), h("span", { text: e.decision }),
      h("span", { text: `${e.durationMs ?? "–"} ms${e.policyName ? ` · ${e.policyName.split("/").pop()}` : ""}` })));
  }
}

async function loadActivityFromLog(runId) {
  // Older recordings may lack hook rows; read them from Failproof's own log now, and say so.
  try {
    const { entries } = await (await fetch(`/api/runs/${encodeURIComponent(runId)}/activity`)).json();
    if (entries.length) {
      addActivity(entries);
      $("activity").prepend(h("li", { class: "empty", text: "Read from Failproof's hook log just now." }));
    }
  } catch { /* the panel keeps its empty state */ }
}

function onVerification(v) {
  const row = (ok, text) => h("li", {}, h("span", { class: ok ? "y" : "n", "aria-hidden": "true", text: ok ? "✓" : "✗" }), h("span", { text }));
  const blockedCount = v.blocked.length;
  $("verify").replaceChildren(
    row(v.original_tests_pass, `Original tests: ${v.original_tests.summary || (v.original_tests_pass ? "passed" : "failed")}`),
    row(v.infra_changed.length === 0, v.infra_changed.length
      ? `Tests/config changed (ignored for the check above): ${v.infra_changed.join(", ")}` : "Tests, pytest config and CI unchanged"),
    row(v.blocked_content_absent, blockedCount ? `Blocked content absent from disk (${blockedCount} checked)` : "No blocked edits to check"),
    row(v.agent_suite.passed, `Agent's own suite: ${v.agent_suite.summary}`));
  const ok = v.original_tests_pass;
  addStep(ok ? "ok" : "error", ok ? "✓" : "✗", h("div", { class: `card ${ok ? "allow" : "deny"}` },
    h("div", { class: "card-top" }, h("strong", { text: ok ? "The original, unmodified tests pass" : "The original tests still fail" }),
      h("span", { class: `state ${ok ? "ok" : "deny"}`, text: v.original_tests.summary })),
    v.diff ? h("details", { class: "final" }, h("summary", { text: "Final patch" }), diffBlock(v.diff.split("\n").filter((l) => !/^(diff --git|index |--- |\+\+\+ )/.test(l)).join("\n"))) : h("p", { class: "note quiet", text: "No changes were made." })));
}

loadScenarios().then(() => { loadHealth(); loadHistory(); });
