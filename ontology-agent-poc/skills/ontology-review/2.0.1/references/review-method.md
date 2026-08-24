# Review Method

Review the sealed denominator, not a convenient sample. Trace each analytical
obligation end to end: requirement, governed metric/rule, formula, population,
properties, bindings, joins and SQL.

For metrics, construct an independent semantic ledger: expected output unit/currency
and scale, operand units, formula scale, filters, denominator behavior and SQL output.
The ledger must reconcile. Explicitly test for currency relabeling, missing FX
conversion, missing or double millions scaling, raw-ratio versus percentage drift,
and formula/SQL disagreement.

Do not repeat a deterministic finding unless exact evidence expands its scope. If
evidence is insufficient, record the uncertainty precisely rather than inventing a
business rule. Advisory severity does not grant release authority.
