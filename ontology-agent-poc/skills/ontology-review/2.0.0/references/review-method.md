# Review method

## Coverage

Review the sealed denominator, not a self-selected sample. Read Candidate pages
with the largest useful bounded page size until the registry reports full disclosure.
Inspect high-risk Candidates in coherent batches and follow dependency references
needed to judge them; do not serialize one Candidate per model turn when a batch fits.

## Evidence and semantic checks

- Requirement and question: answer scope, output grain and stated exclusions agree.
- Metric: base metrics use physical operands; derived metrics use metric references;
  numerator and denominator are not tautological; unit, grain, time semantics,
  eligibility, cancellation and zero-denominator behavior are explicit.
- Data: every governed Property has a compatible physical binding; join keys and
  cardinality are coherent; no field is invented beyond source or an explicit gap.
- SQL: read-only scope, table/column/filter/aggregate/output lineage and ontology
  contracts agree. Plausibility is not proof.
- Graph: references close, duplicated concepts are identified, and relationships do
  not assert business facts unsupported by evidence.
- Language: authoring labels and definitions follow the Solution output language;
  stable IDs, schema keys, formulas and source quotations may remain technical.

## Finding discipline

Do not repeat an existing deterministic finding unless new evidence materially
changes its scope. Advisory findings may be ERROR severity, but must never claim
release-blocking authority. If evidence is insufficient to prove a defect, record
the uncertainty precisely rather than inventing the missing business rule.
