from __future__ import annotations

import importlib.util
from pathlib import Path
import re
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = REPO_ROOT / "multi-thread-coordinator"


def load_script(name: str, filename: str):
    path = SKILL_ROOT / "scripts" / filename
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DeliveryPackageTests(unittest.TestCase):
    def test_installable_skill_has_required_portable_structure(self) -> None:
        self.assertTrue((SKILL_ROOT / "SKILL.md").is_file())
        self.assertTrue((SKILL_ROOT / "agents" / "openai.yaml").is_file())
        self.assertTrue(
            (SKILL_ROOT / "scripts" / "audit_coordination_state.py").is_file()
        )
        self.assertTrue(
            (SKILL_ROOT / "scripts" / "init_generic_workspace.py").is_file()
        )
        self.assertFalse((SKILL_ROOT / "README.md").exists())

    def test_entrypoint_local_markdown_links_resolve_inside_skill(self) -> None:
        entrypoint = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        links = re.findall(r"\[[^]]+\]\(([^)]+)\)", entrypoint)
        local_links = [
            link for link in links if "://" not in link and not link.startswith("#")
        ]
        self.assertTrue(local_links)
        for link in local_links:
            with self.subTest(link=link):
                self.assertTrue((SKILL_ROOT / link).is_file())

    def test_shared_delivery_material_excludes_local_machine_paths(self) -> None:
        shared_files = [REPO_ROOT / "README.md", REPO_ROOT / "THIRD_PARTY_NOTICES.md"]
        shared_files.extend(SKILL_ROOT.rglob("*.md"))
        combined = "\n".join(path.read_text(encoding="utf-8") for path in shared_files)
        self.assertNotRegex(combined, r"[A-Za-z]:\\")
        self.assertNotRegex(combined, r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

    def test_public_distribution_has_license_install_and_safety_guidance(self) -> None:
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        license_text = (REPO_ROOT / "LICENSE").read_text(encoding="utf-8")
        notices = (REPO_ROOT / "THIRD_PARTY_NOTICES.md").read_text(
            encoding="utf-8"
        )

        self.assertIn("crystal-dev128/multi-thread-coordinator", readme)
        self.assertIn("$skill-installer", readme)
        self.assertIn("v0.1.0", readme)
        self.assertIn("Do not add real client data", readme)
        self.assertNotIn("private repository", readme.lower())
        self.assertIn("MIT License", license_text)
        self.assertIn("codex-agent-orchestration-skill", notices)
        self.assertIn("codex-task-messenger", notices)

    def test_user_visible_task_contract_uses_native_completion_events(self) -> None:
        entrypoint = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        protocol = (SKILL_ROOT / "references" / "protocol.md").read_text(
            encoding="utf-8"
        )
        runbook = (SKILL_ROOT / "references" / "mvp-runbook.md").read_text(
            encoding="utf-8"
        )
        staged = (SKILL_ROOT / "references" / "staged-execution.md").read_text(
            encoding="utf-8"
        )
        resilience = (SKILL_ROOT / "references" / "resilience.md").read_text(
            encoding="utf-8"
        )

        self.assertIn("expected_return: task_event", entrypoint)
        self.assertIn("create_thread", entrypoint)
        self.assertIn("wait_threads", entrypoint)
        self.assertIn(
            "expected_return: automatic | task_event | push | manual",
            protocol,
        )
        self.assertIn("clientThreadId", protocol)
        self.assertIn("send_message_to_thread", protocol)
        self.assertIn("Run this event-driven loop", runbook)
        self.assertIn("wait_threads", runbook)
        self.assertIn("fresh task-event wait", staged)
        self.assertIn("return-first barrier", protocol)
        self.assertIn("contract_migration", protocol)
        self.assertIn("coordinator self-review cannot substitute", entrypoint)
        self.assertIn("packet_digest", protocol)
        self.assertIn("pairwise distinct", protocol)
        self.assertIn("one narrow wall-clock exception", protocol)
        self.assertIn(
            "does not relax delivery, first wait, arming, reconciliation", protocol
        )
        self.assertIn("cap nesting depth at 64", protocol)
        self.assertIn("optional_adjudication", protocol)
        self.assertIn("desired_verdict", protocol)
        self.assertIn("accepted_by", resilience)
        self.assertIn("schema_provenance", protocol)
        self.assertIn("migrated_from_v1", protocol)
        self.assertIn("trusted_persisted_attestation", protocol)
        self.assertIn("cryptographic_actor_or_creation_proof: false", protocol)
        self.assertIn("cannot prove actor identity", protocol)
        self.assertIn("--legacy-run", resilience)
        self.assertIn("push_capability", protocol)
        self.assertIn("manual_disclosed_at", protocol)
        self.assertIn("automatic_return", protocol)
        self.assertIn("review_status: effective | superseded", protocol)
        self.assertIn("replacement_review_id", protocol)
        self.assertIn("strictly earlier than the child's", protocol)
        self.assertIn("exact surface/mode matrix", protocol)
        self.assertIn("complete `retry_of` ancestry", protocol)
        self.assertIn("candidate-level `consumes`", protocol)
        self.assertIn("candidate/authority-ambiguous identities fail", protocol)
        self.assertIn("Every attempt on that supersession path is delivered", protocol)
        self.assertIn("same identity domain", protocol)
        self.assertIn("canonical null pointer retains all five keys", protocol)
        self.assertIn("published `latest_result`", protocol)
        candidate_contract = protocol.split("## 8. Candidate and Evidence References", 1)[1]
        candidate_contract = candidate_contract.split("For persisted v2", 1)[0]
        self.assertNotIn("supersedes:", candidate_contract)
        self.assertNotIn(
            "Make a user-visible task push its result",
            entrypoint,
        )

        event_flow = [
            "Create the task through the native user-visible task surface",
            "Call the native event wait capability",
            "Treat `completed` or `needs_attention` as a returned event",
            "Treat a bounded wait timeout as no new event",
        ]
        positions = [protocol.index(step) for step in event_flow]
        self.assertEqual(sorted(positions), positions)

        fail_closed_flow = [
            "Create the task through the native user-visible task surface",
            "capture its returned `threadId` and `hostId`",
            "Call the native event wait capability",
            "and cursor with the attempt",
            "Apply a return-first barrier",
            "The coordinator owns every gate",
        ]
        positions = [protocol.index(step) for step in fail_closed_flow]
        self.assertEqual(sorted(positions), positions)

    def test_provenance_warning_is_identical_across_initializer_and_auditor(self) -> None:
        auditor = load_script("delivery_auditor", "audit_coordination_state.py")
        initializer = load_script("delivery_initializer", "init_generic_workspace.py")
        self.assertEqual(auditor.PROVENANCE_WARNING, initializer.PROVENANCE_WARNING)
        self.assertIn(
            "cannot detect a coordinated full-record rewrite or backfill",
            auditor.PROVENANCE_WARNING,
        )

    def test_host_adapter_covers_codex_and_claude_surfaces(self) -> None:
        hosts_path = SKILL_ROOT / "references" / "hosts.md"
        self.assertTrue(hosts_path.is_file())

        hosts = hosts_path.read_text(encoding="utf-8")
        entrypoint = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        protocol = (SKILL_ROOT / "references" / "protocol.md").read_text(
            encoding="utf-8"
        )
        resilience = (SKILL_ROOT / "references" / "resilience.md").read_text(
            encoding="utf-8"
        )

        # The entrypoint must route to the adapter before a surface is chosen.
        self.assertIn("references/hosts.md", entrypoint)

        # Both hosts are mapped, so neither is the implicit default.
        self.assertIn("| Capability | Codex | Claude Code |", hosts)
        for capability in (
            "spawn_helper",
            "spawn_durable_worker",
            "await_return",
            "read_worker_evidence",
            "worker_push",
            "resume_same_worker",
            "isolate_checkout",
            "worker_identity",
        ):
            with self.subTest(capability=capability):
                self.assertIn(capability, hosts)

        # Codex surfaces stay named, so an installed Codex copy is unchanged.
        for codex_tool in (
            "create_thread",
            "wait_threads",
            "read_thread",
            "send_message_to_thread",
            "threadId",
            "hostId",
            "clientThreadId",
        ):
            with self.subTest(codex_tool=codex_tool):
                self.assertIn(codex_tool, hosts)

        # The adapter is bound by observed capability, not by product name.
        self.assertIn("Detect the Host by Capability, Not by Name", hosts)

        # Both return models are described, and the invariant names the failure
        # rather than one host's transport.
        self.assertIn("Pull return (Codex)", hosts)
        self.assertIn("Re-invocation return (Claude Code)", hosts)
        self.assertIn("### 6a. Two Return Models", protocol)
        self.assertIn("never abandon it or hand the user an unverified", entrypoint)

        # Claude-side limitations are disclosed where they change a recommendation.
        self.assertIn("Workers are scoped to the session", hosts)
        self.assertIn("Do not read a background worker's raw output file", hosts)
        self.assertIn("[hosts.md](hosts.md)", resilience)

        # Missing capabilities degrade in a stated order rather than silently.
        self.assertIn("When a Capability Is Missing", hosts)
        self.assertIn("manual-return", hosts)

    def test_notify_contract_is_documented_as_a_peer_of_task_event(self) -> None:
        hosts = (SKILL_ROOT / "references" / "hosts.md").read_text(encoding="utf-8")
        entrypoint = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        protocol = (SKILL_ROOT / "references" / "protocol.md").read_text(
            encoding="utf-8"
        )
        resilience = (SKILL_ROOT / "references" / "resilience.md").read_text(
            encoding="utf-8"
        )
        auditor = load_script("notify_auditor", "audit_coordination_state.py")
        initializer = load_script("notify_initializer", "init_generic_workspace.py")

        # The executable contract and the documented one agree.
        self.assertEqual("notify_v1", auditor.RETURN_CONTRACT_VERSIONS["notify"])
        self.assertEqual("return_armed_at", auditor.RETURN_READY_FIELDS["notify"])
        self.assertEqual("first_wait_at", auditor.RETURN_READY_FIELDS["task_event"])
        self.assertIn("notify_v1", initializer.ALLOWED_RETURN_CONTRACT_VERSIONS)

        # notify is a peer surface, not a looser one.
        self.assertEqual(
            auditor.RETURN_MODE_OWNER_SURFACES["notify"],
            auditor.RETURN_MODE_OWNER_SURFACES["task_event"],
        )
        self.assertIn("worker_thread_id", auditor.ATTEMPT_MODE_FIELDS["notify"])
        self.assertIn("worker_host_id", auditor.ATTEMPT_MODE_FIELDS["notify"])

        # A resumable wait cursor belongs only to the contract that can resume.
        self.assertNotIn("return_cursor", auditor.ATTEMPT_MODE_FIELDS["notify"])
        self.assertNotIn("first_wait_at", auditor.ATTEMPT_MODE_FIELDS["notify"])
        self.assertNotIn("return_armed_at", auditor.ATTEMPT_MODE_FIELDS["task_event"])

        # Each reference states the contract where a coordinator would look.
        self.assertIn("Persisted Return Contracts", hosts)
        self.assertIn("`notify_v1`", hosts)
        self.assertIn("expected_return: notify", entrypoint)
        self.assertIn("return_contract_version: notify_v1", entrypoint)
        self.assertIn("notify delivery precedes arming", protocol)
        self.assertIn("notify-only: return_armed_at", resilience)

    def test_claude_adapter_states_how_to_surface_worker_work(self) -> None:
        hosts = (SKILL_ROOT / "references" / "hosts.md").read_text(encoding="utf-8")
        entrypoint = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")

        # A worker is not a visible thread on this host, so the coordinator has
        # to relay results and mirror status itself.
        self.assertIn("Make the work visible", hosts)
        self.assertIn("final report is not shown to the user", hosts)
        self.assertIn("native task list", hosts)

        # Relaying is a reporting duty, not an acceptance shortcut.
        self.assertIn("Relaying is not accepting", hosts)

        # The transcript is still not the report.
        self.assertIn("raw transcript is not a report", hosts)

        # The entrypoint routes to the adapter when reporting, not only when
        # choosing a surface.
        self.assertIn("reporting what a worker returned", entrypoint)

if __name__ == "__main__":
    unittest.main()
