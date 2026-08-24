# Evidence-to-Ontology Modeling Method

Trace every business obligation through the smallest coherent chain that makes it
usable and reviewable:

1. requirement or analytical question;
2. governed object, rule, metric or process;
3. properties and relationships required by that meaning;
4. grain, unit, currency, numeric scale, time basis, population and exclusions;
5. physical source, binding, joins, SQL contract and boundary behavior;
6. claim-level Evidence Receipts or an explicit Gap.

Prefer explicit missingness over invented completeness. Keep source codes, physical
identifiers, formulas and SQL exact; translate only human-readable ontology content.

For each metric, build a semantic ledger before completion. Record the intended output
unit/currency/scale, every operand unit, formula scaling, required filters, population,
and SQL output convention. These entries must reconcile. A raw ratio is not a
percentage merely because its label says percent. A USD measure is not HKD without an
evidenced conversion. HKD is not HKD millions without explicit scaling.

For analytical rates, numerator and denominator are governed base metrics with their
own population/filter semantics and physical lineage. The reported rate composes those
metric identities. For SQL-derived values, bind only to the exact derived relation and
named output proven by SQL evidence. SQL factors, predicates and denominator structure
are part of the semantic contract.

The `sources` array is a provenance summary, not a reading list. Every source declared
there must appear in a same-target claim backed by a server-minted receipt. Sample data
may support physical shape, observed domains and quality checks, but not undocumented
business definitions.
