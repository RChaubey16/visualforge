"""Tests for vf_state.py. Run: python3 -m unittest discover -s .claude/skills/website-orchestrator/scripts"""

import contextlib
import hashlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import vf_state  # noqa: E402

ALL_SKILLS = [m["skill"] for m in vf_state.STAGES.values()]


def run(*argv):
    buf = io.StringIO()
    code = 0
    with contextlib.redirect_stdout(buf):
        try:
            vf_state.main(list(argv))
        except SystemExit as exc:
            code = exc.code or 0
    return code, json.loads(buf.getvalue())


def sha(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


class Base(unittest.TestCase):
    skills = ALL_SKILLS

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        for s in self.skills:
            d = self.repo / ".claude" / "skills" / s
            d.mkdir(parents=True)
            (d / "SKILL.md").write_text(f"---\nname: {s}\nmetadata:\n  version: 0.1.0\n---\n")
        code, res = run("init", "--repo", str(self.repo), "--name", "demo",
                        "--url", "https://example.com", "--pages", "home")
        self.assertEqual(code, 0, res)
        self.p = str(self.repo / "projects" / "demo")
        self.project = Path(self.p)

    def tearDown(self):
        self.tmp.cleanup()

    def state(self):
        return json.loads((self.project / "state" / "project-state.json").read_text())

    def fake_stage(self, stage, files, status="completed", checklist_result="pass"):
        """Simulate a stage skill: write outputs and a result file."""
        outputs = []
        for rel, content in files.items():
            f = self.project / rel
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(content)
            outputs.append({"path": rel, "sha256": sha(f)})
        result = {"stage_id": stage, "status": status, "outputs": outputs,
                  "checkpoints": [{"id": "all", "status": "done"}],
                  "quality_checklist": [{"criterion": "c", "result": checklist_result}],
                  "warnings": [], "open_questions": [], "error": None}
        (self.project / "state" / "stages" / f"{stage}.result.json").write_text(json.dumps(result))

    def run_stage(self, stage, files, fix=False, defects=None):
        args = ["envelope", "--project", self.p, "--stage", stage]
        if fix:
            args += ["--mode", "fix", "--defects", defects]
        code, res = run(*args)
        self.assertEqual(code, 0, res)
        self.fake_stage(stage, files)
        args = ["complete", "--project", self.p, "--stage", stage] + (["--fix"] if fix else [])
        code, res = run(*args)
        self.assertEqual(code, 0, res)
        return res

    def ready_through_gate_a(self, browser="available"):
        run("preflight", "--project", self.p, "--browser", browser)
        run("gate", "--project", self.p, "--gate", "A", "--status", "approved")


class InitTests(Base):
    def test_init_creates_workspace_and_state(self):
        st = self.state()
        self.assertEqual(st["run_mode"], "full")
        self.assertTrue((self.project / "brief.md").exists())
        self.assertTrue(all(r["status"] == "pending" for r in st["stages"].values()))
        self.assertEqual(st["config"]["viewports"], [375, 768, 1280, 1440])

    def test_init_refuses_existing_project(self):
        code, res = run("init", "--repo", str(self.repo), "--name", "demo",
                        "--url", "https://example.com")
        self.assertEqual(code, 1)

    def test_init_rejects_bad_name(self):
        code, _ = run("init", "--repo", str(self.repo), "--name", "Bad Name",
                      "--url", "https://example.com")
        self.assertEqual(code, 2)


class FlowTests(Base):
    def test_next_requires_preflight_then_gate_a(self):
        self.assertEqual(run("next", "--project", self.p)[1]["action"], "preflight")
        run("preflight", "--project", self.p, "--browser", "available")
        res = run("next", "--project", self.p)[1]
        self.assertEqual((res["action"], res["gate"]), ("gate", "A"))

    def test_browser_unavailable_blocks_research(self):
        self.ready_through_gate_a(browser="unavailable")
        res = run("next", "--project", self.p)[1]
        self.assertEqual(res["action"], "blocked")
        self.assertIn("browser_unavailable", res["blocked"][0]["reason"])
        self.assertEqual(self.state()["stages"]["S1-research"]["status"], "blocked")

    def test_analysis_pair_runs_in_parallel(self):
        self.ready_through_gate_a()
        self.run_stage("S1-research", {"research/observations.json": "{}"})
        res = run("next", "--project", self.p)[1]
        self.assertEqual(res["stages"], ["S2a-ux", "S2b-design-system"])
        self.assertTrue(res["parallel"])

    def test_gate_b_blocks_architecture(self):
        self.ready_through_gate_a()
        self.run_stage("S1-research", {"research/observations.json": "{}"})
        self.run_stage("S2a-ux", {"analysis/ux-findings.json": "{}"})
        self.run_stage("S2b-design-system", {"design/tokens.json": "{}"})
        self.run_stage("S3-spec", {"specs/sitemap.json": "{}"})
        res = run("next", "--project", self.p)[1]
        self.assertEqual((res["action"], res["gate"]), ("gate", "B"))

    def test_complete_rejects_missing_output_and_allows_one_retry(self):
        self.ready_through_gate_a()
        run("envelope", "--project", self.p, "--stage", "S1-research")
        self.fake_stage("S1-research", {"research/observations.json": "{}"})
        (self.project / "research" / "observations.json").unlink()
        code, res = run("complete", "--project", self.p, "--stage", "S1-research")
        self.assertEqual(code, 1)
        self.assertTrue(res["retry_allowed"])
        run("envelope", "--project", self.p, "--stage", "S1-research")
        run("complete", "--project", self.p, "--stage", "S1-research")
        res = run("next", "--project", self.p)[1]
        self.assertEqual(res["action"], "blocked")
        self.assertIn("retries_exhausted", res["blocked"][0]["reason"])

    def test_complete_rejects_failed_quality_criterion(self):
        self.ready_through_gate_a()
        run("envelope", "--project", self.p, "--stage", "S1-research")
        self.fake_stage("S1-research", {"research/observations.json": "{}"},
                        checklist_result="fail")
        code, res = run("complete", "--project", self.p, "--stage", "S1-research")
        self.assertEqual(code, 1)
        self.assertIn("quality criterion failed", " ".join(res["errors"]))


class MissingSkillTests(Base):
    skills = ["website-orchestrator"]

    def test_missing_stage_skill_blocks_instead_of_skipping(self):
        self.ready_through_gate_a()
        res = run("next", "--project", self.p)[1]
        self.assertEqual(res["action"], "blocked")
        self.assertIn("missing_skill", res["blocked"][0]["reason"])
        # reconcile re-checks on the next session
        res = run("reconcile", "--project", self.p)[1]
        self.assertEqual(res["unblocked"], ["S1-research"])


class PreflightTests(Base):
    skills = ["website-orchestrator", "reference-analyzer"]

    def test_preflight_records_browser_error_and_missing_skills(self):
        code, res = run("preflight", "--project", self.p, "--browser", "unavailable",
                        "--browser-error", "chrome not found")
        self.assertEqual(code, 1)
        self.assertEqual(res["tools"]["browser_error"], "chrome not found")
        self.assertIn("chrome not found", res["tools"]["problems"][0])
        self.assertNotIn("reference-analyzer", res["missing_skills_in_scope"])
        self.assertIn("visual-qa", res["missing_skills_in_scope"])

    def test_missing_skills_scoped_to_mode(self):
        run("next", "--project", self.p, "--mode", "research")
        _, res = run("preflight", "--project", self.p, "--browser", "available")
        self.assertEqual(res["missing_skills_in_scope"], [])


class ModeTests(Base):
    def test_research_mode_stops_after_research(self):
        self.ready_through_gate_a()
        run("next", "--project", self.p, "--mode", "research")
        self.run_stage("S1-research", {"research/observations.json": "{}"})
        res = run("next", "--project", self.p)[1]
        self.assertEqual(res["action"], "done")
        self.assertEqual(self.state()["stages"]["S2a-ux"]["status"], "pending")

    def test_implementation_mode_reports_missing_prerequisites(self):
        run("preflight", "--project", self.p, "--browser", "available")
        res = run("next", "--project", self.p, "--mode", "implementation")[1]
        self.assertEqual(res["action"], "missing_prerequisites")
        self.assertIn("S3-spec", res["stages"])


class ResumeTests(Base):
    def test_interrupted_stage_is_failed_and_completed_stages_kept(self):
        self.ready_through_gate_a()
        self.run_stage("S1-research", {"research/observations.json": "{}"})
        run("envelope", "--project", self.p, "--stage", "S2a-ux")  # crash while running
        res = run("reconcile", "--project", self.p)[1]
        self.assertEqual(res["interrupted"], ["S2a-ux"])
        self.assertIn("S1-research", res["completed_and_valid"])
        nxt = run("next", "--project", self.p)[1]
        self.assertIn("S2a-ux", nxt["stages"])
        self.assertNotIn("S1-research", nxt["stages"])

    def test_manual_edit_marks_stage_and_downstream_stale(self):
        self.ready_through_gate_a()
        self.run_stage("S1-research", {"research/observations.json": "{}"})
        self.run_stage("S2a-ux", {"analysis/ux-findings.json": "{}"})
        (self.project / "research" / "observations.json").write_text('{"edited": true}')
        res = run("reconcile", "--project", self.p)[1]
        self.assertEqual(res["manual_edits"], ["S1-research:research/observations.json"])
        self.assertEqual(res["stale"], ["S1-research", "S2a-ux"])

    def test_brief_change_makes_research_stale(self):
        self.ready_through_gate_a()
        self.run_stage("S1-research", {"research/observations.json": "{}"})
        with (self.project / "brief.md").open("a") as fh:
            fh.write("\nNew constraint.\n")
        res = run("reconcile", "--project", self.p)[1]
        self.assertIn("S1-research", res["stale"])


class QaLoopTests(Base):
    def build_until_qa(self):
        self.ready_through_gate_a()
        for stage, f in [("S1-research", "research/observations.json"),
                         ("S2a-ux", "analysis/ux-findings.json"),
                         ("S2b-design-system", "design/tokens.json"),
                         ("S3-spec", "specs/sitemap.json")]:
            self.run_stage(stage, {f: "{}"})
        run("gate", "--project", self.p, "--gate", "B", "--status", "approved")
        for stage, f in [("S4-architecture", "site/package.json"),
                         ("S5-implement", "site/src/page.tsx"),
                         ("S6-motion", "site/src/motion.tsx")]:
            self.run_stage(stage, {f: "x"})

    def write_defects(self, n, defects):
        d = self.project / "qa" / f"iteration-{n}"
        d.mkdir(parents=True, exist_ok=True)
        (d / "defects.json").write_text(json.dumps({"defects": defects}))
        return f"qa/iteration-{n}/defects.json"

    def test_fix_loop_routes_and_reruns_qa_only(self):
        self.build_until_qa()
        f = self.write_defects(1, [
            {"id": "def-1-001", "severity": "major", "owner_skill": "frontend-implementer",
             "status": "open"},
            {"id": "def-1-002", "severity": "minor", "owner_skill": "motion-engineer",
             "status": "open"}])
        self.run_stage("S7-qa", {f: (self.project / f).read_text()})
        self.assertEqual(run("next", "--project", self.p)[1]["action"], "qa_loop")
        res = run("qa", "--project", self.p)[1]
        self.assertEqual(res["decision"], "fix")
        self.assertEqual(res["routes"]["S5-implement"]["defects"], ["def-1-001"])
        fixed = self.run_stage("S5-implement", {"site/src/page.tsx": "fixed"}, fix=True,
                               defects="def-1-001")
        self.assertEqual(fixed["now_stale"], ["S7-qa"])  # S8 never ran, stays pending
        st = self.state()["stages"]
        self.assertEqual(st["S6-motion"]["status"], "completed")
        # S6 is not re-run on resume because its fingerprint was refreshed
        self.assertNotIn("S6-motion", run("reconcile", "--project", self.p)[1]["stale"])
        self.assertEqual(run("next", "--project", self.p)[1]["stages"], ["S7-qa"])

    def test_budget_exhaustion_and_acceptance(self):
        self.build_until_qa()
        run("gate", "--project", self.p, "--gate", "A", "--status", "approved")
        state_file = self.project / "state" / "project-state.json"
        st = json.loads(state_file.read_text())
        st["config"]["qa_budget"] = 1
        state_file.write_text(json.dumps(st))
        f = self.write_defects(1, [{"id": "def-1-001", "severity": "blocker",
                                    "owner_skill": "frontend-implementer", "status": "open"}])
        self.run_stage("S7-qa", {f: (self.project / f).read_text()})
        self.assertEqual(run("qa", "--project", self.p)[1]["decision"], "budget_exhausted")
        run("qa", "--project", self.p, "--accept", "user accepts known issue")
        self.assertEqual(run("next", "--project", self.p)[1]["stages"], ["S8-release"])

    def test_invalid_defects_file_is_reported_not_crashed(self):
        self.build_until_qa()
        f = self.write_defects(1, [])
        (self.project / f).write_text("not json")
        code, res = run("qa", "--project", self.p)
        self.assertEqual(code, 1)
        self.assertIn("not a valid defects file", res["error"])

    def test_pass_then_release_then_gate_c(self):
        self.build_until_qa()
        f = self.write_defects(1, [])
        self.run_stage("S7-qa", {f: (self.project / f).read_text()})
        self.assertEqual(run("qa", "--project", self.p)[1]["decision"], "pass")
        self.run_stage("S8-release", {"release/release-report.md": "ok"})
        res = run("next", "--project", self.p)[1]
        self.assertEqual((res["action"], res["gate"]), ("gate", "C"))
        run("gate", "--project", self.p, "--gate", "C", "--status", "approved")
        self.assertEqual(run("next", "--project", self.p)[1]["action"], "done")


if __name__ == "__main__":
    unittest.main()
