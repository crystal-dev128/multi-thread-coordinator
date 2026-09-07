from contextlib import contextmanager
from contextlib import redirect_stdout
import importlib.util
from io import StringIO
import json
import shutil
import unittest
import uuid
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = (
    REPO_ROOT
    / "multi-thread-coordinator"
    / "scripts"
    / "init_generic_workspace.py"
)
SPEC = importlib.util.spec_from_file_location("init_generic_workspace", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
WORKSPACE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(WORKSPACE)

SKILL_COMMIT = "f12670de41bbac81dd33e4c2eebf3173bcc8aec4"
COORDINATOR_ID = "coordinator_main"


@contextmanager
def isolated_parent():
    container = REPO_ROOT / "tests" / ".tmp-init-generic-workspace"
    container.mkdir(exist_ok=True)
    case = container / f"case-{uuid.uuid4().hex}"
    case.mkdir()
    try:
        yield case
    finally:
        shutil.rmtree(case)
        try:
            container.rmdir()
        except OSError:
            pass


def make_binding(
    project_root: Path,
    *,
    mode: str = "generic_workspace",
    workspace_layout: str | None = "adopted_folder",
) -> dict:
    if workspace_layout == "managed_intake":
        read_roots = ["HUMAN_PORTAL/01_DROP_FILES_HERE"]
        write_roots = ["AGENT_WORKSPACE", "HUMAN_PORTAL/02_RESULTS"]
    else:
        read_roots = ["."]
        write_roots = ["AGENT_WORKSPACE", "RESULTS"]
    return {
        "binding_version": 1,
        "binding_id": "binding_v001",
        "mode": mode,
        "workspace_layout": workspace_layout if mode == "generic_workspace" else None,
        "project_root": str(project_root.resolve()),
        "coordination_root": "AGENT_WORKSPACE" if mode == "generic_workspace" else None,
        "workflow_authority": None if mode == "generic_workspace" else "workflow/config.json",
        "authorities": [],
        "read_roots": read_roots,
        "write_roots": write_roots,
        "forbidden_paths": [],
        "single_writer_rules": [],
        "validation_surfaces": [],
        "external_actions": {
            "network": "ask",
            "publish": "ask",
            "destructive": "prohibited",
        },
        "data_boundary": "synthetic local test workspace",
    }


def initialize_workspace(*args, **kwargs):
    kwargs.setdefault("skill_commit_at_creation", SKILL_COMMIT)
    kwargs.setdefault("coordinator_id", COORDINATOR_ID)
    return WORKSPACE.initialize(*args, **kwargs)


class GenericWorkspaceInitializationTests(unittest.TestCase):
    def write_binding(self, parent: Path, project_root: Path, **kwargs) -> Path:
        path = parent / "binding.json"
        path.write_text(
            json.dumps(make_binding(project_root, **kwargs), indent=2),
            encoding="utf-8",
        )
        return path

    def test_dry_run_creates_nothing(self) -> None:
        with isolated_parent() as parent:
            project = parent / "project"
            project.mkdir()
            binding = self.write_binding(parent, project)

            report = initialize_workspace(
                project, binding, "batch_0001", "run_0001", dry_run=True
            )

            self.assertTrue(report["dry_run"])
            self.assertEqual("adopted_folder", report["workspace_layout"])
            self.assertTrue(report["would_create"])
            self.assertIn("RESULTS/", report["would_create"])
            self.assertNotIn("HUMAN_PORTAL/", report["would_create"])
            self.assertFalse((project / "HUMAN_PORTAL").exists())
            self.assertFalse((project / "RESULTS").exists())
            self.assertFalse((project / "AGENT_WORKSPACE").exists())

    def test_initialization_is_idempotent_and_preserves_progress(self) -> None:
        with isolated_parent() as parent:
            project = parent / "project"
            project.mkdir()
            source = project / "source.txt"
            source.write_text("original synthetic input\n", encoding="utf-8")
            source_before = source.read_bytes()
            binding = self.write_binding(parent, project)

            first = initialize_workspace(project, binding, "batch_0001", "run_0001")
            self.assertTrue(first["created"])
            self.assertEqual("adopted_folder", first["workspace_layout"])
            self.assertEqual(
                "trusted_persisted_attestation", first["provenance_trust_model"]
            )
            self.assertFalse(first["cryptographic_actor_or_creation_proof"])
            self.assertEqual([WORKSPACE.PROVENANCE_WARNING], first["warnings"])
            self.assertIn(
                "cannot detect a coordinated full-record rewrite or backfill",
                WORKSPACE.PROVENANCE_WARNING,
            )
            self.assertTrue((project / "RESULTS").is_dir())
            self.assertFalse((project / "HUMAN_PORTAL").exists())
            self.assertEqual(source_before, source.read_bytes())
            latest_path = project / "AGENT_WORKSPACE" / "03_outputs" / "latest_result.json"
            latest = json.loads(latest_path.read_text(encoding="utf-8"))
            self.assertIsNone(latest["run_id"])
            self.assertIsNone(latest["candidate_id"])

            run_path = (
                project
                / "AGENT_WORKSPACE"
                / "02_working"
                / "run_0001"
                / "coordination"
                / "run.json"
            )
            run_record = json.loads(run_path.read_text(encoding="utf-8"))
            self.assertEqual(2, run_record["schema_version"])
            self.assertEqual(SKILL_COMMIT, run_record["skill_commit_at_creation"])
            self.assertEqual("task_event_v1", run_record["return_contract_version"])
            self.assertEqual(COORDINATOR_ID, run_record["coordinator_id"])
            self.assertEqual("created_v2", run_record["schema_provenance"]["mode"])
            self.assertEqual(
                WORKSPACE._canonical_sha256(
                    WORKSPACE._creation_snapshot(
                        run_record,
                        run_record["schema_provenance"]["established_at"],
                    )
                ),
                run_record["schema_provenance"]["creation_digest"],
            )
            self.assertEqual([], run_record["attempts"])
            self.assertEqual([], run_record["reviews"])
            self.assertEqual([], run_record["active_work"])
            run_record["tasks"].append({"task_id": "task_demo", "status": "running"})
            run_path.write_text(json.dumps(run_record, indent=2), encoding="utf-8")
            before_repeat = run_path.read_text(encoding="utf-8")

            second = initialize_workspace(project, binding, "batch_0001", "run_0001")

            self.assertEqual([], second["created"])
            self.assertIn(
                "AGENT_WORKSPACE/02_working/run_0001/coordination/run.json",
                second["validated"],
            )
            self.assertEqual(before_repeat, run_path.read_text(encoding="utf-8"))
            self.assertFalse(
                (project / "AGENT_WORKSPACE" / "02_working" / "run_0001" / "shared").exists()
            )
            self.assertFalse(
                (
                    project
                    / "AGENT_WORKSPACE"
                    / "02_working"
                    / "run_0001"
                    / "coordination"
                    / "recovery.json"
                ).exists()
            )
            self.assertFalse(
                (
                    project
                    / "AGENT_WORKSPACE"
                    / "03_outputs"
                    / "run_0001"
                    / "result_manifest.json"
                ).exists()
            )

    def test_existing_schema_one_run_is_preserved_as_legacy_history(self) -> None:
        with isolated_parent() as parent:
            project = parent / "project"
            project.mkdir()
            binding = self.write_binding(parent, project)
            initialize_workspace(project, binding, "batch_0001", "run_0001")
            run_path = (
                project
                / "AGENT_WORKSPACE"
                / "02_working"
                / "run_0001"
                / "coordination"
                / "run.json"
            )
            run_record = json.loads(run_path.read_text(encoding="utf-8"))
            run_record["schema_version"] = 1
            for field in (
                "skill_commit_at_creation",
                "return_contract_version",
                "coordinator_id",
                "schema_provenance",
            ):
                run_record.pop(field)
            run_record["tasks"] = [
                {"task_id": "task_legacy", "status": "pending"}
            ]
            run_path.write_text(
                json.dumps(run_record, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            before_repeat = run_path.read_bytes()

            report = initialize_workspace(
                project, binding, "batch_0001", "run_0001"
            )

            self.assertIn(
                "AGENT_WORKSPACE/02_working/run_0001/coordination/run.json",
                report["validated"],
            )
            self.assertEqual(before_repeat, run_path.read_bytes())
            self.assertEqual(
                1, json.loads(run_path.read_text(encoding="utf-8"))["schema_version"]
            )

    def test_v2_requires_all_record_lists_while_v1_may_omit_them(self) -> None:
        with isolated_parent() as parent:
            project = parent / "project"
            project.mkdir()
            binding = self.write_binding(parent, project)
            initialize_workspace(project, binding, "batch_0001", "run_0001")
            run_path = (
                project
                / "AGENT_WORKSPACE"
                / "02_working"
                / "run_0001"
                / "coordination"
                / "run.json"
            )
            run_record = json.loads(run_path.read_text(encoding="utf-8"))

            for field in WORKSPACE.RUN_LIST_FIELDS:
                with self.subTest(contract="v2", field=field):
                    value = run_record.pop(field)
                    run_path.write_text(
                        json.dumps(run_record, indent=2), encoding="utf-8"
                    )
                    with self.assertRaisesRegex(
                        WORKSPACE.WorkspaceInitError,
                        f"existing run.json {field} is required for schema_version 2",
                    ):
                        initialize_workspace(
                            project, binding, "batch_0001", "run_0001"
                        )
                    run_record[field] = value

            run_record["schema_version"] = 1
            for field in (
                "skill_commit_at_creation",
                "return_contract_version",
                "coordinator_id",
                "schema_provenance",
                *WORKSPACE.RUN_LIST_FIELDS,
            ):
                run_record.pop(field)
            run_path.write_text(
                json.dumps(run_record, indent=2), encoding="utf-8"
            )

            report = initialize_workspace(
                project, binding, "batch_0001", "run_0001"
            )
            self.assertIn(
                "AGENT_WORKSPACE/02_working/run_0001/coordination/run.json",
                report["validated"],
            )

    def test_existing_schema_two_run_without_creation_provenance_is_rejected(self) -> None:
        with isolated_parent() as parent:
            project = parent / "project"
            project.mkdir()
            binding = self.write_binding(parent, project)
            initialize_workspace(project, binding, "batch_0001", "run_0001")
            run_path = (
                project
                / "AGENT_WORKSPACE"
                / "02_working"
                / "run_0001"
                / "coordination"
                / "run.json"
            )
            run_record = json.loads(run_path.read_text(encoding="utf-8"))
            run_record.pop("schema_provenance")
            run_path.write_text(json.dumps(run_record, indent=2), encoding="utf-8")

            with self.assertRaisesRegex(
                WORKSPACE.WorkspaceInitError,
                "lacks a created_v2 structural schema_provenance attestation",
            ):
                initialize_workspace(project, binding, "batch_0001", "run_0001")

    def test_initializer_schema_discriminators_reject_booleans(self) -> None:
        with isolated_parent() as parent:
            project = parent / "project"
            project.mkdir()
            binding = self.write_binding(parent, project)
            initialize_workspace(project, binding, "batch_0001", "run_0001")

            manifest_path = (
                project
                / "AGENT_WORKSPACE"
                / "01_raw_inputs"
                / "batch_0001"
                / "manifest.json"
            )
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["schema_version"] = True
            manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            with self.assertRaisesRegex(
                WORKSPACE.WorkspaceInitError,
                "existing manifest.json has conflicting schema_version",
            ):
                initialize_workspace(project, binding, "batch_0001", "run_0001")
            manifest["schema_version"] = 1
            manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

            run_path = (
                project
                / "AGENT_WORKSPACE"
                / "02_working"
                / "run_0001"
                / "coordination"
                / "run.json"
            )
            run_record = json.loads(run_path.read_text(encoding="utf-8"))
            run_record["schema_version"] = True
            run_path.write_text(json.dumps(run_record, indent=2), encoding="utf-8")
            with self.assertRaisesRegex(
                WORKSPACE.WorkspaceInitError,
                "existing run.json has unsupported schema_version",
            ):
                initialize_workspace(project, binding, "batch_0001", "run_0001")
            run_record["schema_version"] = 2
            run_path.write_text(json.dumps(run_record, indent=2), encoding="utf-8")

            stored_binding_path = (
                project
                / "AGENT_WORKSPACE"
                / "00_project_config"
                / "workspace_binding.json"
            )
            stored_binding = json.loads(
                stored_binding_path.read_text(encoding="utf-8")
            )
            stored_binding["binding_version"] = True
            stored_binding_path.write_text(
                json.dumps(stored_binding, indent=2), encoding="utf-8"
            )
            with self.assertRaisesRegex(
                WORKSPACE.WorkspaceInitError,
                "existing workspace_binding.json has conflicting binding_version",
            ):
                initialize_workspace(project, binding, "batch_0001", "run_0001")
            stored_binding["binding_version"] = 1
            stored_binding_path.write_text(
                json.dumps(stored_binding, indent=2), encoding="utf-8"
            )

            binding_record = json.loads(binding.read_text(encoding="utf-8"))
            binding_record["binding_version"] = True
            binding.write_text(json.dumps(binding_record, indent=2), encoding="utf-8")
            with self.assertRaisesRegex(
                WORKSPACE.WorkspaceInitError,
                "binding_version must be 1",
            ):
                initialize_workspace(project, binding, "batch_0001", "run_0001")

    def test_existing_latest_result_requires_the_exact_canonical_pointer_schema(self) -> None:
        with isolated_parent() as parent:
            project = parent / "project"
            project.mkdir()
            binding = self.write_binding(parent, project)
            initialize_workspace(project, binding, "batch_0001", "run_0001")
            latest_path = project / "AGENT_WORKSPACE" / "03_outputs" / "latest_result.json"
            canonical = json.loads(latest_path.read_text(encoding="utf-8"))
            pointer = dict(canonical)
            pointer["verdict"] = "current"
            latest_path.write_text(json.dumps(pointer, indent=2), encoding="utf-8")

            with self.assertRaisesRegex(
                WORKSPACE.WorkspaceInitError,
                "unsupported: verdict",
            ):
                initialize_workspace(project, binding, "batch_0001", "run_0001")

            invalid_pointers = {
                "boolean schema": (
                    {**canonical, "schema_version": True},
                    "conflicting schema_version",
                ),
                "partial null": (
                    {**canonical, "run_id": "run_0001"},
                    "fully-null pointer or four non-empty string pointer fields",
                ),
                "empty value": (
                    {
                        **canonical,
                        "run_id": "run_0001",
                        "result_manifest": "",
                        "candidate_id": "candidate_001",
                        "source_digest": "digest",
                    },
                    "fully-null pointer or four non-empty string pointer fields",
                ),
                "whitespace value": (
                    {
                        **canonical,
                        "run_id": "run_0001",
                        "result_manifest": "result_manifest.json",
                        "candidate_id": "   ",
                        "source_digest": "digest",
                    },
                    "fully-null pointer or four non-empty string pointer fields",
                ),
            }
            for label, (invalid, expected) in invalid_pointers.items():
                with self.subTest(label=label):
                    latest_path.write_text(
                        json.dumps(invalid, indent=2), encoding="utf-8"
                    )
                    with self.assertRaisesRegex(
                        WORKSPACE.WorkspaceInitError, expected
                    ):
                        initialize_workspace(
                            project, binding, "batch_0001", "run_0001"
                        )

            populated = {
                "schema_version": 1,
                "run_id": "run_0001",
                "result_manifest": "run_0001/result_manifest.json",
                "candidate_id": "candidate_001",
                "source_digest": "source-digest",
            }
            latest_path.write_text(json.dumps(populated, indent=2), encoding="utf-8")
            report = initialize_workspace(project, binding, "batch_0001", "run_0001")
            self.assertIn(
                "AGENT_WORKSPACE/03_outputs/latest_result.json", report["validated"]
            )

    def test_managed_intake_layout_is_explicit_opt_in(self) -> None:
        with isolated_parent() as parent:
            project = parent / "project"
            project.mkdir()
            binding = self.write_binding(
                parent, project, workspace_layout="managed_intake"
            )

            report = initialize_workspace(
                project, binding, "batch_0001", "run_0001"
            )

            self.assertEqual("managed_intake", report["workspace_layout"])
            self.assertTrue(
                (project / "HUMAN_PORTAL" / "01_DROP_FILES_HERE").is_dir()
            )
            self.assertTrue((project / "HUMAN_PORTAL" / "02_RESULTS").is_dir())
            self.assertFalse((project / "RESULTS").exists())

    def test_invalid_workspace_layout_is_rejected_without_creation(self) -> None:
        with isolated_parent() as parent:
            project = parent / "project"
            project.mkdir()
            binding = self.write_binding(
                parent, project, workspace_layout="unexpected_layout"
            )

            with self.assertRaises(WORKSPACE.WorkspaceInitError):
                initialize_workspace(project, binding, "batch_0001", "run_0001")

            self.assertEqual([], list(project.iterdir()))

    def test_missing_workspace_layout_is_rejected_without_creation(self) -> None:
        with isolated_parent() as parent:
            project = parent / "project"
            project.mkdir()
            binding_value = make_binding(project)
            binding_value.pop("workspace_layout")
            binding = parent / "binding.json"
            binding.write_text(json.dumps(binding_value, indent=2), encoding="utf-8")

            with self.assertRaises(WORKSPACE.WorkspaceInitError):
                initialize_workspace(project, binding, "batch_0001", "run_0001")

            self.assertEqual([], list(project.iterdir()))

    def test_layout_change_requires_explicit_binding_update(self) -> None:
        with isolated_parent() as parent:
            project = parent / "project"
            project.mkdir()
            binding = self.write_binding(parent, project)
            initialize_workspace(project, binding, "batch_0001", "run_0001")

            binding.write_text(
                json.dumps(
                    make_binding(project, workspace_layout="managed_intake"), indent=2
                ),
                encoding="utf-8",
            )
            with self.assertRaises(WORKSPACE.WorkspaceInitError):
                initialize_workspace(project, binding, "batch_0001", "run_0001")

            self.assertTrue((project / "RESULTS").is_dir())
            self.assertFalse((project / "HUMAN_PORTAL").exists())

    def test_conflicting_binding_aborts_before_other_creation(self) -> None:
        with isolated_parent() as parent:
            project = parent / "project"
            project.mkdir()
            binding = self.write_binding(parent, project)

            config = project / "AGENT_WORKSPACE" / "00_project_config"
            config.mkdir(parents=True)
            conflicting = make_binding(project)
            conflicting["data_boundary"] = "different boundary"
            (config / "workspace_binding.json").write_text(
                json.dumps(conflicting, indent=2), encoding="utf-8"
            )

            with self.assertRaises(WORKSPACE.WorkspaceInitError):
                initialize_workspace(project, binding, "batch_0001", "run_0001")

            self.assertFalse((project / "RESULTS").exists())
            self.assertFalse((project / "HUMAN_PORTAL").exists())
            stored = json.loads((config / "workspace_binding.json").read_text(encoding="utf-8"))
            self.assertEqual("different boundary", stored["data_boundary"])

    def test_existing_workflow_binding_is_rejected_without_creation(self) -> None:
        with isolated_parent() as parent:
            project = parent / "project"
            project.mkdir()
            binding = self.write_binding(parent, project, mode="existing_workflow")

            with self.assertRaises(WORKSPACE.WorkspaceInitError):
                initialize_workspace(project, binding, "batch_0001", "run_0001")

            self.assertEqual([], list(project.iterdir()))

    def test_cli_dry_run_returns_audit_json(self) -> None:
        with isolated_parent() as parent:
            project = parent / "project"
            project.mkdir()
            binding = self.write_binding(parent, project)
            output = StringIO()

            with redirect_stdout(output):
                exit_code = WORKSPACE.main(
                    [
                        "--project-root",
                        str(project),
                        "--binding",
                        str(binding),
                        "--batch-id",
                        "batch_0001",
                        "--run-id",
                        "run_0001",
                        "--skill-commit-at-creation",
                        SKILL_COMMIT,
                        "--coordinator-id",
                        COORDINATOR_ID,
                        "--dry-run",
                    ]
                )

            self.assertEqual(0, exit_code)
            report = json.loads(output.getvalue())
            self.assertTrue(report["dry_run"])
            self.assertEqual("binding_v001", report["binding_id"])
            self.assertEqual("adopted_folder", report["workspace_layout"])
            self.assertTrue(report["would_create"])
            self.assertEqual([], list(project.iterdir()))

    def test_invalid_existing_task_status_is_rejected(self) -> None:
        with isolated_parent() as parent:
            project = parent / "project"
            project.mkdir()
            binding = self.write_binding(parent, project)
            initialize_workspace(project, binding, "batch_0001", "run_0001")

            run_path = (
                project
                / "AGENT_WORKSPACE"
                / "02_working"
                / "run_0001"
                / "coordination"
                / "run.json"
            )
            run_record = json.loads(run_path.read_text(encoding="utf-8"))
            run_record["tasks"].append({"task_id": "task_demo", "status": "approved"})
            run_path.write_text(json.dumps(run_record, indent=2), encoding="utf-8")

            with self.assertRaises(WORKSPACE.WorkspaceInitError):
                initialize_workspace(project, binding, "batch_0001", "run_0001")


if __name__ == "__main__":
    unittest.main()
