# Evidence-to-Ontology Modeling Method

The output is not a bag of extracted nouns and formulas. It is the smallest connected
model that lets a human verify what the business asks, what each concept means, how
the answer is computed, which data supports it, and where uncertainty remains.

Trace every analytical obligation through this product chain:

1. business process and analytical requirement;
2. governed question family and expected answer shape;
3. analysis pattern and its applicable dimensions, policies, and boundaries;
4. objects, properties, relationships, rules, metrics, and accountable actors;
5. population, exclusions, grain, unit, currency, scale, time basis, and lifecycle;
6. physical source, field binding, join path, and SQL contract;
7. claim-level Evidence Receipts or an explicit Gap.

This is an output completeness map, not a mandatory reasoning order. Explore and
repair in whichever order best fits the evidence. Use the Build Objective's required
collection types as the machine-enforced minimum shape for each obligation.

Prefer explicit missingness over invented completeness. Keep source codes, physical
identifiers, formulas, and SQL exact. Translate only human-readable ontology content
into the requested output language.

For each metric, maintain a semantic ledger: output unit/currency/scale, operand
units, formula scale, filters, population, denominator behavior, and SQL convention.
A label never repairs an incompatible calculation. Model physical types exactly;
represent any logical conversion as an explicit governed Binding transformation.
Represent derived eligibility as a governed Rule referenced by
`query.population_rule`; use `query.population_property` only for an evidenced
boolean eligibility field. A date property is required for temporal scoping, while a
period property exists only when the source model actually supplies a period ID.
Row-level expressions such as elapsed duration remain base metrics; a derived metric
is reserved for formulas that compose governed metric references.

When the Build Objective exposes a `metric_semantic_contract`, close the obligation
with its exact `expected_metric_id`. Reconcile every raw source field in that contract
before authoring. The normalized guards cover only mechanically explicit identity,
unit and scale rules; they do not replace reading the evidence or modeling the actual
business numerator, denominator, population and physical lineage.

Candidate identity, status and source provenance are shell-owned metadata. The model
selects exact receipts and claim support; the shell deterministically derives the
logical source IDs written to the Candidate.
