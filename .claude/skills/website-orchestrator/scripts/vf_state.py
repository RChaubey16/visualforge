#!/usr/bin/env python3
"""VisualForge project state manager (stdlib only).

The website-orchestrator skill uses this script for every state transition so
that stage ordering, resume, validation and the QA loop are deterministic.
Every command prints a JSON object on stdout. Exit code 0 = ok, 1 = the
command ran but reports a problem (e.g. validation failed), 2 = usage error.

Commands (all take --project <projects/<name> dir> except init):
  init        create project workspace, brief skeleton and state
  preflight   record tool availability (CLI checks + browser flag)
  lock/unlock acquire or release the orchestrator lock
  reconcile   resume logic: interrupted stages, hash checks, staleness
  next        compute the next runnable stages for the current mode
  envelope    write an invocation envelope and mark the stage running
  complete    validate a stage's result file and mark it completed
  fail        mark a stage failed (retryable) or blocked
  gate        record a gate decision
  qa          evaluate the latest QA iteration and decide the loop action
  invalidate  mark a stage and everything downstream stale
  status      write state/status.md and print a summary
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = "1.0"

# Stage catalog. Mirrors docs/architecture/workflow.md and skill-contracts.md.
STAGES: dict[str, dict] = {
    "S0-init": {"skill": "website-orchestrator", "deps": [], "gate_before": None,
                "browser": False, "inputs": {}, "output_dir": "state/"},
    "S1-research": {"skill": "reference-analyzer", "deps": ["S0-init"], "gate_before": "A",
                    "browser": "required", "inputs": {"brief": "brief.md"},
                    "output_dir": "research/"},
    "S2a-ux": {"skill": "ux-design-analyst", "deps": ["S1-research"], "gate_before": None,
               "browser": False, "parallel_group": "analysis",
               "inputs": {"brief": "brief.md", "observations": "research/observations.json",
                          "research_report": "research/research-report.md",
                          "pages_dir": "research/pages"},
               "output_dir": "analysis/"},
    "S2b-design-system": {"skill": "design-system-extractor", "deps": ["S1-research"],
                          "gate_before": None, "browser": False, "parallel_group": "analysis",
                          "inputs": {"brief": "brief.md",
                                     "observations": "research/observations.json",
                                     "pages_dir": "research/pages", "motion_dir": "research/motion"},
                          "output_dir": "design/"},
    "S3-spec": {"skill": "page-specification", "deps": ["S2a-ux", "S2b-design-system"],
                "gate_before": None, "browser": False,
                "inputs": {"brief": "brief.md", "ux_findings": "analysis/ux-findings.json",
                           "tokens": "design/tokens.json",
                           "design_system": "design/design-system.md"},
                "output_dir": "specs/"},
    "S4-architecture": {"skill": "nextjs-architect", "deps": ["S3-spec"], "gate_before": "B",
                        "browser": False,
                        "inputs": {"sitemap": "specs/sitemap.json", "page_specs": "specs/pages",
                                   "tokens": "design/tokens.json",
                                   "motion_spec": "specs/motion-spec.json"},
                        "output_dir": "site/"},
    "S5-implement": {"skill": "frontend-implementer", "deps": ["S4-architecture"],
                     "gate_before": None, "browser": "optional",
                     "inputs": {"component_inventory": "architecture/component-inventory.json",
                                "page_specs": "specs/pages", "content": "specs/content",
                                "tokens": "design/tokens.json", "site": "site"},
                     "output_dir": "site/"},
    "S6-motion": {"skill": "motion-engineer", "deps": ["S5-implement"], "gate_before": None,
                  "browser": "optional",
                  "inputs": {"motion_spec": "specs/motion-spec.json",
                             "tokens": "design/tokens.json", "site": "site"},
                  "output_dir": "site/"},
    "S7-qa": {"skill": "visual-qa", "deps": ["S6-motion"], "gate_before": None,
              "browser": "required",
              "inputs": {"site": "site", "specs": "specs", "tokens": "design/tokens.json",
                         "ux_findings": "analysis/ux-findings.json",
                         "reference_pages": "research/pages"},
              "output_dir": "qa/"},
    "S8-release": {"skill": "release-auditor", "deps": ["S7-qa"], "gate_before": None,
                   "browser": False,
                   "inputs": {"site": "site", "qa_summary": "qa/summary.json", "specs": "specs",
                              "design": "design",
                              "assets_inventory": "research/assets-inventory.json",
                              "brief": "brief.md"},
                   "output_dir": "release/"},
}
ORDER = list(STAGES)
OWNER_STAGE = {meta["skill"]: sid for sid, meta in STAGES.items()}
FIXABLE_OWNERS = {"design-system-extractor", "page-specification", "nextjs-architect",
                  "frontend-implementer", "motion-engineer"}

# Execution modes: the set of stages the run may execute. Anything upstream of
# the scope must already be completed, otherwise `next` reports it as a
# missing prerequisite (never silently skipped).
MODES = {
    "full": ORDER,
    "research": ["S0-init", "S1-research"],
    "design-spec": ["S0-init", "S1-research", "S2a-ux", "S2b-design-system", "S3-spec"],
    "implementation": ["S4-architecture", "S5-implement", "S6-motion"],
    "visual-qa": ["S7-qa"],
}
MODE_FINAL_GATE = {"full": "C", "design-spec": "B"}
MAX_ATTEMPTS = 2  # first attempt + one retry, then blocked
LOCK_STALE_SECONDS = 6 * 3600
DEFAULT_VIEWPORTS = [375, 768, 1280, 1440]
SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


# ----------------------------------------------------------------- helpers

def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def out(obj: dict, code: int = 0) -> None:
    print(json.dumps(obj, indent=2))
    sys.exit(code)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode()).hexdigest()


def write_json_atomic(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n")
    os.replace(tmp, path)


def state_path(project: Path) -> Path:
    return project / "state" / "project-state.json"


def load_state(project: Path) -> dict:
    p = state_path(project)
    if not p.exists():
        out({"ok": False, "error": f"no state file at {p}; run init first"}, 1)
    return json.loads(p.read_text())


def save_state(project: Path, state: dict) -> None:
    write_json_atomic(state_path(project), state)


def log(project: Path, event: str, stage: str | None = None, **extra) -> None:
    entry = {"at": now(), "event": event, "stage": stage, **extra}
    with (project / "state" / "run-log.jsonl").open("a") as fh:
        fh.write(json.dumps(entry) + "\n")


def repo_root(project: Path) -> Path:
    # projects/<name> lives two levels below the repository root.
    return project.resolve().parent.parent


def skill_installed(project: Path, skill: str) -> bool:
    return (repo_root(project) / ".claude" / "skills" / skill / "SKILL.md").exists()


def skill_version(project: Path, skill: str) -> str:
    md = repo_root(project) / ".claude" / "skills" / skill / "SKILL.md"
    if not md.exists():
        return "0.0.0"
    m = re.search(r"^\s*version:\s*[\"']?([0-9][^\"'\s]*)", md.read_text(), re.M)
    return m.group(1) if m else "0.0.0"


def downstream(stage: str) -> list[str]:
    result, frontier = [], [stage]
    while frontier:
        cur = frontier.pop()
        for sid, meta in STAGES.items():
            if cur in meta["deps"] and sid not in result:
                result.append(sid)
                frontier.append(sid)
    return sorted(result, key=ORDER.index)


def upstream(stage: str) -> list[str]:
    result, frontier = [], list(STAGES[stage]["deps"])
    while frontier:
        cur = frontier.pop()
        if cur not in result:
            result.append(cur)
            frontier.extend(STAGES[cur]["deps"])
    return sorted(result, key=ORDER.index)


def fingerprint(project: Path, state: dict, stage: str) -> str:
    """Hash of everything the stage consumed: predecessor outputs, brief, config, skill version."""
    parts = [f"skill={STAGES[stage]['skill']}@{skill_version(project, STAGES[stage]['skill'])}",
             f"config={json.dumps(state['config'], sort_keys=True)}"]
    brief = project / "brief.md"
    if brief.exists():
        parts.append(f"brief={sha256_file(brief)}")
    for dep in STAGES[stage]["deps"]:
        for path, digest in sorted(state["stages"][dep].get("outputs", {}).items()):
            parts.append(f"{dep}:{path}={digest}")
    return sha256_text("\n".join(parts))


def new_stage_record() -> dict:
    return {"status": "pending", "run": 0, "attempts": 0, "skill_version": None,
            "input_fingerprint": None, "outputs": {}, "started_at": None,
            "finished_at": None, "checkpoints_done": 0, "checkpoints_total": 0,
            "error": None, "blocked_reason": None}


def mark_stale(project: Path, state: dict, stage: str, reason: str) -> list[str]:
    changed = []
    for sid in [stage] + downstream(stage):
        rec = state["stages"][sid]
        if rec["status"] == "completed":
            rec["status"] = "stale"
            rec["error"] = None
            changed.append(sid)
            log(project, "stage_stale", sid, reason=reason)
    return changed


# ---------------------------------------------------------------- commands

def cmd_init(a) -> None:
    repo = Path(a.repo).resolve()
    if not SLUG_RE.match(a.name):
        out({"ok": False, "error": "project name must be kebab-case"}, 2)
    if not re.match(r"^https?://", a.url):
        out({"ok": False, "error": "reference URL must start with http:// or https://"}, 2)
    if a.mode not in MODES:
        out({"ok": False, "error": f"mode must be one of {sorted(MODES)}"}, 2)
    project = repo / "projects" / a.name
    if state_path(project).exists():
        out({"ok": False, "error": f"project {a.name} already exists; use resume",
             "project": str(project)}, 1)
    for d in ["state/stages", "state/envelopes", "state/locks", "research", "analysis",
              "design", "specs", "architecture", "build", "qa", "release"]:
        (project / d).mkdir(parents=True, exist_ok=True)
    pages = [p.strip() for p in a.pages.split(",") if p.strip()]
    viewports = [int(v) for v in a.viewports.split(",")] if a.viewports else DEFAULT_VIEWPORTS
    state = {
        "schema_version": SCHEMA_VERSION,
        "project": {"name": a.name, "reference_url": a.url, "created_at": now()},
        "run_mode": a.mode,
        "config": {"viewports": viewports, "qa_budget": a.qa_budget,
                   "commits_authorised": False, "target_pages": pages},
        "tools": {},
        "gates": {g: {"status": "pending"} for g in ("A", "B", "C")},
        "stages": {sid: new_stage_record() for sid in ORDER},
        "qa": {"iteration": 0, "open": {"blocker": 0, "major": 0, "minor": 0},
               "decision": None},
        "git": {"branch": None, "last_commit": None},
    }
    brief = project / "brief.md"
    if not brief.exists():
        brief.write_text(
            "---\nproject: {name}\nreference_url: {url}\nrun_mode: {mode}\ncreated_at: {at}\n---\n\n"
            "# Project brief: {name}\n\n"
            "## Reference\n- URL: {url}\n- Target pages: {pages}\n\n"
            "## Original brand\n- Name: {brand}\n- Positioning: {positioning}\n\n"
            "## Audience\n{audience}\n\n"
            "## Constraints\n{constraints}\n\n"
            "## Configuration\n- Viewports: {vps}\n- QA iteration budget: {budget}\n".format(
                name=a.name, url=a.url, mode=a.mode, at=now(), pages=", ".join(pages) or "TBD",
                brand=a.brand or "TBD", positioning=a.positioning or "TBD",
                audience=a.audience or "TBD", constraints=a.constraints or "None stated.",
                vps=", ".join(map(str, viewports)), budget=a.qa_budget))
    save_state(project, state)
    log(project, "project_initialised", "S0-init", mode=a.mode)
    out({"ok": True, "project": str(project), "brief": str(brief),
         "next": "run preflight, complete the brief, then request Gate A"})


def _cli_version(cmd: list[str]) -> str | None:
    if not shutil.which(cmd[0]):
        return None
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
    except (subprocess.TimeoutExpired, OSError):
        return None
    text = (res.stdout or res.stderr).strip().splitlines()
    return text[0] if res.returncode == 0 and text else None


def cmd_preflight(a) -> None:
    project = Path(a.project)
    state = load_state(project)
    node = _cli_version(["node", "--version"])
    node_ok = False
    if node:
        m = re.match(r"v(\d+)\.(\d+)", node)
        node_ok = bool(m) and (int(m.group(1)), int(m.group(2))) >= (20, 9)
    tools = {
        "checked_at": now(),
        "browser_mcp": a.browser,
        "node": {"version": node, "ok": node_ok, "required_for": "S4-S8"},
        "npm": {"version": _cli_version(["npm", "--version"]), "required_for": "S4-S8"},
        "npx": {"version": _cli_version(["npx", "--version"]), "required_for": "S4-S8"},
        "git": {"version": _cli_version(["git", "--version"]), "required_for": "commits"},
        "python3": {"version": _cli_version(["python3", "--version"]),
                    "required_for": "orchestrator"},
    }
    if a.browser_error:
        tools["browser_error"] = a.browser_error
    missing_skills = [m["skill"] for sid, m in STAGES.items()
                      if sid != "S0-init" and not skill_installed(project, m["skill"])]
    tools["missing_skills"] = missing_skills
    problems = []
    if a.browser != "available":
        problems.append("Browser unavailable" + (f" ({a.browser_error})" if a.browser_error else "")
                        + ": S1-research and S7-qa cannot run.")
    if not node_ok:
        problems.append("Node.js >= 20.9 not found: implementation stages (S4-S8) cannot run.")
    for name in ("npm", "npx", "git"):
        if not tools[name]["version"]:
            problems.append(f"{name} not found.")
    tools["problems"] = problems
    state["tools"] = tools
    rec = state["stages"]["S0-init"]
    if rec["status"] != "completed":
        rec.update(status="completed", run=1, skill_version=skill_version(
            project, "website-orchestrator"), finished_at=now(),
            input_fingerprint=fingerprint(project, state, "S0-init"),
            outputs={"brief.md": sha256_file(project / "brief.md")})
    save_state(project, state)
    log(project, "preflight", "S0-init", browser=a.browser, problems=len(problems))
    in_scope = [STAGES[s]["skill"] for s in MODES[state["run_mode"]]
                if s != "S0-init" and STAGES[s]["skill"] in missing_skills]
    out({"ok": not problems, "tools": tools,
         "missing_skills_in_scope": in_scope,
         "note": "Stages whose skill is missing will block when reached; tell the user now."
                 if in_scope else None}, 1 if problems else 0)


def cmd_lock(a) -> None:
    project = Path(a.project)
    lock = project / "state" / "locks" / "orchestrator.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    if lock.exists():
        info = json.loads(lock.read_text())
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(
            info["at"].replace("Z", "+00:00"))).total_seconds()
        if age < LOCK_STALE_SECONDS and not a.force:
            out({"ok": False, "error": "another orchestrator run holds the lock",
                 "lock": info, "hint": "if no other session is running this project, "
                 "re-run with --force after confirming with the user"}, 1)
        log(project, "lock_recovered", None, previous=info)
    lock.write_text(json.dumps({"at": now(), "session": a.session or "unknown"}))
    out({"ok": True, "lock": str(lock)})


def cmd_unlock(a) -> None:
    lock = Path(a.project) / "state" / "locks" / "orchestrator.lock"
    if lock.exists():
        lock.unlink()
    out({"ok": True})


def cmd_reconcile(a) -> None:
    project = Path(a.project)
    state = load_state(project)
    report = {"interrupted": [], "stale": [], "manual_edits": [], "missing_outputs": [],
              "unblocked": []}
    for sid in ORDER:
        rec = state["stages"][sid]
        if rec["status"] == "running":
            rec.update(status="failed", error="interrupted: stage was running when the "
                       "previous session ended; partial output is not trusted")
            report["interrupted"].append(sid)
            log(project, "stage_interrupted", sid)
        if rec["status"] == "blocked" and rec.get("blocked_reason") in (
                "missing_skill", "browser_unavailable"):
            rec.update(status="pending", error=None, blocked_reason=None)
            report["unblocked"].append(sid)
    for sid in ORDER:
        rec = state["stages"][sid]
        if rec["status"] != "completed" or sid == "S0-init":
            continue
        for rel, digest in rec.get("outputs", {}).items():
            p = project / rel
            if not p.exists():
                report["missing_outputs"].append(f"{sid}:{rel}")
            elif sha256_file(p) != digest:
                report["manual_edits"].append(f"{sid}:{rel}")
                log(project, "manual_edit_detected", sid, path=rel)
        if any(x.startswith(sid + ":") for x in report["missing_outputs"] + report["manual_edits"]):
            report["stale"] += mark_stale(project, state, sid, "outputs changed or missing")
            continue
        if rec.get("input_fingerprint") != fingerprint(project, state, sid):
            report["stale"] += mark_stale(project, state, sid, "inputs changed")
    report["stale"] = sorted(set(report["stale"]), key=ORDER.index)
    save_state(project, state)
    completed = [s for s in ORDER if state["stages"][s]["status"] == "completed"]
    out({"ok": True, **report, "completed_and_valid": completed,
         "note": "manual_edits require asking the user: keep the edit (re-run downstream) "
                 "or regenerate the stage" if report["manual_edits"] else None})


def _blocked_by_env(project: Path, state: dict, sid: str) -> str | None:
    meta = STAGES[sid]
    if sid != "S0-init" and not skill_installed(project, meta["skill"]):
        return "missing_skill"
    if meta["browser"] == "required" and state.get("tools", {}).get("browser_mcp") != "available":
        return "browser_unavailable"
    return None


def cmd_next(a) -> None:
    project = Path(a.project)
    state = load_state(project)
    if a.mode:
        if a.mode not in MODES:
            out({"ok": False, "error": f"unknown mode {a.mode}"}, 2)
        state["run_mode"] = a.mode
    mode = state["run_mode"]
    scope = MODES[mode]
    st = state["stages"]
    if not state.get("tools"):
        save_state(project, state)
        out({"ok": True, "action": "preflight", "message": "run preflight before any stage"})

    # Prerequisites outside the scope must already be completed.
    missing_prereqs = sorted({u for s in scope for u in upstream(s)
                              if u not in scope and st[u]["status"] != "completed"},
                             key=ORDER.index)
    if missing_prereqs:
        save_state(project, state)
        out({"ok": True, "action": "missing_prerequisites", "mode": mode,
             "stages": missing_prereqs,
             "message": "These stages are required before this mode can run. Ask the user "
                        "whether to run them (switch to a wider mode) or stop."})

    if mode == "implementation" and state["gates"]["B"]["status"] != "approved":
        out({"ok": True, "action": "gate", "gate": "B",
             "message": "Implementation requires the approved specification (Gate B)."})

    ready, blocked, waiting_gate, failed_terminal = [], [], None, []
    for sid in scope:
        rec = st[sid]
        if rec["status"] == "completed":
            continue
        if rec["status"] == "blocked":
            blocked.append({"stage": sid, "reason": rec.get("blocked_reason") or rec["error"]})
            continue
        if rec["status"] == "running":
            out({"ok": False, "error": f"{sid} is marked running; run reconcile first"}, 1)
        if not all(st[d]["status"] == "completed" for d in STAGES[sid]["deps"]):
            continue
        gate = STAGES[sid]["gate_before"]
        if gate and state["gates"][gate]["status"] != "approved":
            waiting_gate = waiting_gate or gate
            continue
        if sid == "S8-release" and state["qa"].get("decision") not in ("pass", "accepted"):
            save_state(project, state)
            out({"ok": True, "action": "qa_loop", "mode": mode,
                 "decision": state["qa"].get("decision"),
                 "message": "Release audit waits for the QA loop: run `qa`, route fixes, "
                            "or record the user's acceptance with `qa --accept`."})
        if rec["status"] == "failed" and rec["attempts"] >= MAX_ATTEMPTS:
            rec.update(status="blocked", blocked_reason="retries_exhausted")
            log(project, "stage_blocked", sid, reason="retries_exhausted")
            failed_terminal.append(sid)
            blocked.append({"stage": sid, "reason": "retries_exhausted: " + str(rec["error"])})
            continue
        env = _blocked_by_env(project, state, sid)
        if env:
            msg = (f"skill '{STAGES[sid]['skill']}' is not installed in .claude/skills"
                   if env == "missing_skill" else
                   "Playwright MCP browser tools are unavailable; this stage needs a real browser")
            rec.update(status="blocked", blocked_reason=env, error=msg)
            log(project, "stage_blocked", sid, reason=env)
            blocked.append({"stage": sid, "reason": f"{env}: {msg}"})
            continue
        ready.append(sid)
    save_state(project, state)

    if ready:
        groups = {STAGES[s].get("parallel_group") for s in ready}
        parallel = len(ready) > 1 and len(groups) == 1 and None not in groups
        run = ready if parallel else ready[:1]
        out({"ok": True, "action": "run", "mode": mode, "stages": run, "parallel": parallel,
             "skills": {s: STAGES[s]["skill"] for s in run},
             "also_blocked": blocked})
    if blocked:
        out({"ok": True, "action": "blocked", "mode": mode, "blocked": blocked,
             "message": "Report each blocker to the user with its remedy. Do not skip it."})
    if waiting_gate:
        out({"ok": True, "action": "gate", "gate": waiting_gate, "mode": mode})
    if all(st[s]["status"] == "completed" for s in scope):
        final_gate = MODE_FINAL_GATE.get(mode)
        if final_gate and state["gates"][final_gate]["status"] != "approved":
            out({"ok": True, "action": "gate", "gate": final_gate, "mode": mode})
        out({"ok": True, "action": "done", "mode": mode,
             "message": "All stages in scope are completed. Write the project report."})
    out({"ok": True, "action": "waiting", "mode": mode,
         "message": "No stage is runnable; inspect status."})


def cmd_envelope(a) -> None:
    project = Path(a.project)
    state = load_state(project)
    sid = a.stage
    if sid not in STAGES or sid == "S0-init":
        out({"ok": False, "error": f"unknown or non-invocable stage {sid}"}, 2)
    rec = state["stages"][sid]
    unmet = [d for d in STAGES[sid]["deps"] if state["stages"][d]["status"] != "completed"]
    if unmet and a.mode == "run":
        out({"ok": False, "error": f"dependencies not completed: {unmet}"}, 1)
    if a.mode == "fix" and not (a.defects or a.feedback):
        out({"ok": False, "error": "fix mode needs --defects or --feedback"}, 2)
    rec["run"] += 1
    rec["attempts"] += 1
    rec.update(status="running", started_at=now(), error=None)
    envelope = {
        "project_root": f"projects/{state['project']['name']}",
        "stage_id": sid,
        "skill": STAGES[sid]["skill"],
        "run": rec["run"],
        "mode": a.mode,
        "inputs": {k: v for k, v in STAGES[sid]["inputs"].items()},
        "output_dir": STAGES[sid]["output_dir"],
        "result_path": f"state/stages/{sid}.result.json",
        "config": state["config"],
        "defects": a.defects.split(",") if a.defects else [],
        "feedback": a.feedback,
        "resume_from_checkpoint": a.checkpoint,
    }
    if sid == "S7-qa":
        envelope["qa_iteration"] = state["qa"]["iteration"] + 1
    path = project / "state" / "envelopes" / f"{sid}.run{rec['run']}.json"
    write_json_atomic(path, envelope)
    save_state(project, state)
    log(project, "stage_started", sid, run=rec["run"], mode=a.mode)
    out({"ok": True, "envelope": str(path), "skill": STAGES[sid]["skill"],
         "result_path": str(project / envelope["result_path"])})


def _validate_result(project: Path, sid: str) -> tuple[list[str], dict | None]:
    p = project / "state" / "stages" / f"{sid}.result.json"
    if not p.exists():
        return [f"result file missing: {p}"], None
    try:
        res = json.loads(p.read_text())
    except json.JSONDecodeError as exc:
        return [f"result file is not valid JSON: {exc}"], None
    errors = []
    for key in ("stage_id", "status", "outputs", "quality_checklist", "checkpoints"):
        if key not in res:
            errors.append(f"result missing '{key}'")
    if res.get("stage_id") not in (None, sid):
        errors.append(f"result stage_id {res.get('stage_id')} != {sid}")
    if res.get("status") != "completed":
        errors.append(f"skill reported status '{res.get('status')}': {res.get('error')}")
    outputs = res.get("outputs") or []
    if not outputs:
        errors.append("no outputs declared")
    for o in outputs:
        rel = o.get("path", "")
        f = project / rel
        if rel.startswith("/") or ".." in Path(rel).parts:
            errors.append(f"output path must be project-relative: {rel}")
        elif not f.is_file():
            errors.append(f"declared output missing: {rel}")
        elif o.get("sha256") and o["sha256"] != sha256_file(f):
            errors.append(f"hash mismatch for {rel}")
    for item in res.get("quality_checklist") or []:
        if item.get("result") == "fail":
            errors.append(f"quality criterion failed: {item.get('criterion')}")
    for cp in res.get("checkpoints") or []:
        if cp.get("status") in ("pending", "failed"):
            errors.append(f"checkpoint {cp.get('id')} is {cp.get('status')}")
    if not res.get("quality_checklist"):
        errors.append("empty quality_checklist")
    return errors, res


def cmd_complete(a) -> None:
    project = Path(a.project)
    state = load_state(project)
    sid = a.stage
    rec = state["stages"][sid]
    errors, res = _validate_result(project, sid)
    if res and res.get("status") == "blocked":
        # The skill itself hit something only the user can resolve (bot wall, missing access).
        rec.update(status="blocked", blocked_reason="stage_reported",
                   error=res.get("error") or "stage reported blocked", finished_at=now())
        save_state(project, state)
        log(project, "stage_blocked", sid, reason=rec["error"])
        out({"ok": False, "stage": sid, "blocked": True, "error": rec["error"],
             "open_questions": res.get("open_questions", [])}, 1)
    if errors:
        rec.update(status="failed", error="; ".join(errors), finished_at=now())
        save_state(project, state)
        log(project, "stage_failed", sid, errors=errors)
        out({"ok": False, "stage": sid, "errors": errors,
             "attempts": rec["attempts"], "retry_allowed": rec["attempts"] < MAX_ATTEMPTS}, 1)
    rec.update(status="completed", error=None, blocked_reason=None, attempts=0,
               finished_at=now(), skill_version=skill_version(project, STAGES[sid]["skill"]),
               outputs={o["path"]: sha256_file(project / o["path"]) for o in res["outputs"]},
               checkpoints_total=len(res.get("checkpoints", [])),
               checkpoints_done=sum(1 for c in res.get("checkpoints", [])
                                    if c.get("status") in ("done", "skipped")))
    rec["input_fingerprint"] = fingerprint(project, state, sid)
    stale = []
    if a.fix:
        if sid in ("S4-architecture", "S5-implement", "S6-motion"):
            # Build fixes are targeted: completed build stages downstream accept the new
            # upstream (their fingerprints are refreshed); verification must run again.
            for d in downstream(sid):
                drec = state["stages"][d]
                if d in ("S5-implement", "S6-motion") and drec["status"] == "completed":
                    drec["input_fingerprint"] = fingerprint(project, state, d)
                elif drec["status"] == "completed":
                    drec["status"] = "stale"
                    stale.append(d)
                    log(project, "stage_stale", d, reason=f"fix in {sid}")
        else:
            # Design-system or spec fixes change the build contract: full cascade.
            stale = mark_stale(project, state, sid, f"fix in {sid}")
            stale = [s for s in stale if s != sid]
            rec["status"] = "completed"
    save_state(project, state)
    log(project, "stage_completed", sid, run=rec["run"], fix=bool(a.fix))
    out({"ok": True, "stage": sid, "now_stale": stale, "warnings": res.get("warnings", []),
         "open_questions": res.get("open_questions", []),
         "recapture_requests": res.get("recapture_requests", []),
         "resolved_defects": res.get("resolved_defects", [])})


def cmd_fail(a) -> None:
    project = Path(a.project)
    state = load_state(project)
    rec = state["stages"][a.stage]
    if a.blocked:
        rec.update(status="blocked", error=a.reason, blocked_reason=a.blocked_reason or "other")
    else:
        rec.update(status="failed", error=a.reason)
    rec["finished_at"] = now()
    save_state(project, state)
    log(project, "stage_blocked" if a.blocked else "stage_failed", a.stage, reason=a.reason)
    out({"ok": True, "stage": a.stage, "status": rec["status"],
         "retry_allowed": not a.blocked and rec["attempts"] < MAX_ATTEMPTS})


def cmd_gate(a) -> None:
    project = Path(a.project)
    state = load_state(project)
    g = state["gates"][a.gate]
    g.update(status=a.status, at=now(), notes=a.notes or "")
    save_state(project, state)
    log(project, f"gate_{a.status}", None, gate=a.gate)
    out({"ok": True, "gate": a.gate, "status": a.status})


def cmd_qa(a) -> None:
    project = Path(a.project)
    state = load_state(project)
    if a.accept:
        state["qa"]["decision"] = "accepted"
        state["qa"]["accepted_note"] = a.accept
        save_state(project, state)
        log(project, "qa_accepted", "S7-qa", note=a.accept)
        out({"ok": True, "decision": "accepted"})
    if a.extend:
        state["config"]["qa_budget"] += a.extend
        save_state(project, state)
        log(project, "qa_budget_extended", "S7-qa", budget=state["config"]["qa_budget"])
        out({"ok": True, "qa_budget": state["config"]["qa_budget"]})
    if a.defects_file:
        dfile = project / a.defects_file
        n = state["qa"]["iteration"]
    else:
        iters = sorted((p for p in (project / "qa").glob("iteration-*")
                        if p.name.split("-")[1].isdigit()),
                       key=lambda p: int(p.name.split("-")[1]))
        if not iters:
            out({"ok": False, "error": "no qa/iteration-* directory found"}, 1)
        latest = iters[-1]
        n = int(latest.name.split("-")[1])
        dfile = latest / "defects.json"
    if not dfile.exists():
        out({"ok": False, "error": f"{dfile} missing"}, 1)
    try:
        defects = json.loads(dfile.read_text()).get("defects", [])
    except (json.JSONDecodeError, AttributeError) as exc:
        out({"ok": False, "error": f"{dfile} is not a valid defects file: {exc}"}, 1)
    open_d = [d for d in defects if d.get("status", "open") == "open"]
    counts = {s: sum(1 for d in open_d if d.get("severity") == s)
              for s in ("blocker", "major", "minor")}
    blocking = [d for d in open_d if d.get("severity") in ("blocker", "major")]
    routes: dict[str, list[str]] = {}
    unroutable = []
    for d in blocking:
        owner = d.get("owner_skill")
        if owner in FIXABLE_OWNERS:
            routes.setdefault(OWNER_STAGE[owner], []).append(d["id"])
        else:
            unroutable.append(d.get("id"))
    state["qa"].update(iteration=n, open=counts)
    budget = state["config"]["qa_budget"]
    if not blocking:
        decision = "pass"
    elif n >= budget:
        decision = "budget_exhausted"
    else:
        decision = "fix"
    if state["run_mode"] == "visual-qa" and decision == "fix":
        decision = "report_only"  # QA-only mode reports; fixes need the user's go-ahead
    state["qa"]["decision"] = decision
    save_state(project, state)
    log(project, "qa_iteration", "S7-qa", iteration=n, decision=decision, counts=counts)
    out({"ok": True, "iteration": n, "budget": budget, "decision": decision, "open": counts,
         "routes": {s: {"skill": STAGES[s]["skill"], "defects": ids}
                    for s, ids in sorted(routes.items(), key=lambda kv: ORDER.index(kv[0]))},
         "unroutable": unroutable,
         "minor_defects": [d["id"] for d in open_d if d.get("severity") == "minor"]})


def cmd_invalidate(a) -> None:
    project = Path(a.project)
    state = load_state(project)
    changed = mark_stale(project, state, a.stage, a.reason)
    if a.only_downstream and a.stage in changed:
        state["stages"][a.stage]["status"] = "completed"
        changed.remove(a.stage)
    save_state(project, state)
    out({"ok": True, "stale": changed})


def cmd_status(a) -> None:
    project = Path(a.project)
    state = load_state(project)
    lines = [f"# Status: {state['project']['name']}", "",
             f"- Reference: {state['project']['reference_url']}",
             f"- Mode: {state['run_mode']}",
             f"- Gates: " + ", ".join(f"{g}={v['status']}" for g, v in state["gates"].items()),
             f"- QA: iteration {state['qa']['iteration']}, open {state['qa']['open']}, "
             f"decision {state['qa'].get('decision')}", "",
             "| Stage | Skill | Status | Run | Note |", "|---|---|---|---|---|"]
    for sid in ORDER:
        r = state["stages"][sid]
        note = (r.get("error") or "").replace("|", "/")[:120]
        lines.append(f"| {sid} | {STAGES[sid]['skill']} | {r['status']} | {r['run']} | {note} |")
    problems = state.get("tools", {}).get("problems", [])
    if problems:
        lines += ["", "## Tool problems", *[f"- {p}" for p in problems]]
    (project / "state" / "status.md").write_text("\n".join(lines) + "\n")
    out({"ok": True, "status_file": str(project / "state" / "status.md"),
         "mode": state["run_mode"], "gates": {g: v["status"] for g, v in state["gates"].items()},
         "stages": {s: state["stages"][s]["status"] for s in ORDER}})


# -------------------------------------------------------------------- main

def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    def with_project(name: str) -> argparse.ArgumentParser:
        sp = sub.add_parser(name)
        sp.add_argument("--project", required=True, help="path to projects/<name>")
        return sp

    sp = sub.add_parser("init")
    sp.add_argument("--repo", required=True)
    sp.add_argument("--name", required=True)
    sp.add_argument("--url", required=True)
    sp.add_argument("--pages", default="home", help="comma-separated target page slugs")
    sp.add_argument("--mode", default="full")
    sp.add_argument("--brand")
    sp.add_argument("--positioning")
    sp.add_argument("--audience")
    sp.add_argument("--constraints")
    sp.add_argument("--viewports")
    sp.add_argument("--qa-budget", type=int, default=3)
    sp.set_defaults(fn=cmd_init)

    sp = with_project("preflight")
    sp.add_argument("--browser", required=True, choices=["available", "unavailable"],
                    help="result of the real browser probe (navigate to about:blank + snapshot)")
    sp.add_argument("--browser-error", help="error message from a failed browser probe")
    sp.set_defaults(fn=cmd_preflight)

    sp = with_project("lock")
    sp.add_argument("--force", action="store_true")
    sp.add_argument("--session")
    sp.set_defaults(fn=cmd_lock)
    with_project("unlock").set_defaults(fn=cmd_unlock)
    with_project("reconcile").set_defaults(fn=cmd_reconcile)

    sp = with_project("next")
    sp.add_argument("--mode", choices=sorted(MODES))
    sp.set_defaults(fn=cmd_next)

    sp = with_project("envelope")
    sp.add_argument("--stage", required=True)
    sp.add_argument("--mode", default="run", choices=["run", "fix"])
    sp.add_argument("--defects")
    sp.add_argument("--feedback")
    sp.add_argument("--checkpoint")
    sp.set_defaults(fn=cmd_envelope)

    sp = with_project("complete")
    sp.add_argument("--stage", required=True, choices=ORDER)
    sp.add_argument("--fix", action="store_true", help="the run was a fix-mode run")
    sp.set_defaults(fn=cmd_complete)

    sp = with_project("fail")
    sp.add_argument("--stage", required=True, choices=ORDER)
    sp.add_argument("--reason", required=True)
    sp.add_argument("--blocked", action="store_true")
    sp.add_argument("--blocked-reason")
    sp.set_defaults(fn=cmd_fail)

    sp = with_project("gate")
    sp.add_argument("--gate", required=True, choices=["A", "B", "C"])
    sp.add_argument("--status", required=True, choices=["requested", "approved", "rejected"])
    sp.add_argument("--notes")
    sp.set_defaults(fn=cmd_gate)

    sp = with_project("qa")
    sp.add_argument("--defects-file", help="project-relative defects file (e.g. "
                    "release/defects.json); default: latest qa/iteration-*/defects.json")
    sp.add_argument("--accept", metavar="NOTE",
                    help="record the user's acceptance of remaining defects")
    sp.add_argument("--extend", type=int, metavar="N", help="add N iterations to the budget")
    sp.set_defaults(fn=cmd_qa)

    sp = with_project("invalidate")
    sp.add_argument("--stage", required=True, choices=ORDER)
    sp.add_argument("--reason", required=True)
    sp.add_argument("--only-downstream", action="store_true")
    sp.set_defaults(fn=cmd_invalidate)

    with_project("status").set_defaults(fn=cmd_status)

    args = p.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
