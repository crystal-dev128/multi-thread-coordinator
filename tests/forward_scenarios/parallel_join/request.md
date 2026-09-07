Use the multi-thread coordinator to produce two independent regional guidance notes and then one combined registry.

Run the two regional note tasks concurrently when their preflight proves this is safe.

Required outputs:

- `outputs/north.md` from `north.json`;
- `outputs/south.md` from `south.json`;
- `outputs/registry.json`, created only after both regional notes are accepted.

Each note must list every source program exactly once, preserve its title and audience, and state the regional total duration. The registry must identify both exact accepted note candidates, their SHA-256 digests, and the combined duration.

Constraints:

- Source JSON files are immutable.
- Regional notes are acceptance-independent and have disjoint paths.
- No two active workers may write `outputs/registry.json` or another overlapping path.
- Use internal workers only when they materially help; inspect their real files before acceptance.
- Do not use network access or modify the source fixture directory.
