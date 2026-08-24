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

Prefer explicit missingness over invented completeness. A required relationship,
rule, process, question, pattern, or join that cannot be supported becomes a Gap; it
does not disappear and it is not replaced by a nearby metric. Keep source codes,
physical identifiers, formulas, and SQL exact. Translate only human-readable ontology
content into the requested output language.

For each metric, maintain a semantic ledger: intended output unit/currency/scale,
operand units, formula scale, required filters, population, denominator behavior, and
SQL output convention. A raw ratio is not a percentage because its label says so. A
USD amount is not HKD without evidenced conversion. HKD is not HKD millions without
explicit scaling.

The `sources` array is a provenance summary, not a reading list. Each source declared
on a Candidate must appear in a same-target claim backed by a server receipt. Sample
data may support physical shape and observed values, but not undocumented business
definitions.
