Use the multi-thread coordinator to repair this synthetic order-import workflow and produce `summary.json`.

The cause is not given. Work progressively: diagnose with reproducible evidence, choose the smallest correction from the accepted diagnosis, implement only that correction, and verify both the summary and protected source data. Do not skip directly to an assumed fix.

Constraints:

- Treat `orders.psv` as immutable authoritative input.
- `import_orders.py` and `config.json` may be changed only in the isolated test workspace.
- Do not use network access or modify the source fixture directory.
- The accepted result must contain three orders, total amount `37.50`, and regional totals `North=25.50`, `South=12.00`.
- Return exact candidate identities and primary evidence, not only a completion statement.
