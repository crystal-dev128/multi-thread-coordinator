Use the multi-thread coordinator to resume this interrupted synthetic run safely.

The prior mutating attempt timed out after transport delivery. `recovery.json` records uncertainty, while `outputs/candidate.txt` may contain a real side effect. Inspect native-equivalent records and the candidate before deciding whether to reuse, supersede, or retry. Do not blindly repeat the write operation.

Finish with a reconciled `run.json`, a current `latest_result.json`, preserved recovery evidence, and a passing closure audit from the Skill's read-only audit script. The candidate must contain exactly one `operation_id=op-001` line.

Constraints:

- Work only inside the isolated test copy.
- No network or external actions.
- Preserve the original uncertain attempt in history.
