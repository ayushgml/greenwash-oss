// Greenwash Live guard: a Failproof AI convention policy installed into the sandbox repo
// at .failproofai/policies/. It sends every PreToolUse payload to the Python guard, which
// asks Jev the same questions as the Greenwash PR scanner, and enforces the answer.
//
// Failproof treats a policy that throws or runs past 10s as ALLOW, so every failure path
// here must return deny() explicitly. The spawn timeout (8s) stays under that limit.
import { customPolicies, allow, deny } from "failproofai";
import { spawnSync } from "node:child_process";

const SPAWN_TIMEOUT_MS = 8000;

function evaluate(ctx) {
  const python = process.env.GREENWASH_PYTHON;
  if (!python) {
    return deny("Greenwash guard is not configured (GREENWASH_PYTHON is unset). Guarded actions are denied.");
  }
  const payload = JSON.stringify({
    toolName: ctx.toolName ?? null,
    toolInput: ctx.toolInput ?? null,
    sessionId: ctx.session?.sessionId ?? null,
    cwd: ctx.session?.cwd ?? null,
    // Outside a Greenwash Live run, the guard reads the operator's prompts from here.
    transcriptPath: ctx.session?.transcriptPath ?? ctx.payload?.transcript_path ?? null,
  });
  const result = spawnSync(python, ["-m", "greenwash.guard"], {
    input: payload,
    encoding: "utf8",
    timeout: SPAWN_TIMEOUT_MS,
    env: process.env,
    maxBuffer: 1024 * 1024,
  });
  if (result.error || result.status !== 0) {
    const why = result.error?.code === "ETIMEDOUT" ? "timed out" : `failed (${result.error?.code ?? `exit ${result.status}`})`;
    return deny(`Greenwash guard ${why}; the action was not judged, so it is denied.`);
  }
  const lines = String(result.stdout).trim().split("\n");
  let verdict;
  try {
    verdict = JSON.parse(lines[lines.length - 1]);
  } catch {
    return deny("Greenwash guard returned an unreadable decision; the action is denied.");
  }
  if (verdict?.decision === "allow") return allow();
  const reason = typeof verdict?.reason === "string" && verdict.reason ? verdict.reason : "Greenwash guard denied this action.";
  return deny(`${reason} [attempt ${verdict?.attempt_id ?? "?"}]`);
}

customPolicies.add({
  name: "greenwash-guard",
  description: "Jev judges proposed edits with Greenwash's checks before they run (Greenwash Live)",
  match: { events: ["PreToolUse"] },
  fn: async (ctx) => {
    try {
      return evaluate(ctx);
    } catch (err) {
      return deny(`Greenwash guard crashed (${err?.name ?? "error"}); the action is denied.`);
    }
  },
});
