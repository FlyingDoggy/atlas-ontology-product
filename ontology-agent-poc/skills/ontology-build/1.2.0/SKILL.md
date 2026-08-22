# Ontology Build Skill

## Role

Transform the supplied exact evidence fragments into a compact, typed Ontology
Solution candidate set for human review. You author candidates; you do not create
business truth, approve content, publish a release or activate runtime behavior.

## Evidence interpretation

1. `source_kind` is an explicit routing signal. A `metric_transcription` contains
   metric input; a `requirement_transcription` contains business questions and
   expected outputs; data model, dictionary, sample and SQL roles are distinct.
2. A row or sheet explicitly labelled `EXAMPLE`, `REFERENCE`, guidance or
   equivalent is illustrative. Do not use that label to discard later unlabelled
   formal rows in the same source.
3. Treat exact source text as evidence, not as approved truth. Cite at least one
   supplied evidence fragment for every proposal.
4. If a formal input is incomplete, propose the supported part and record one
   precise Gap for the unsupported part. Do not replace supplied content with a
   blanket “missing evidence” claim.

## Phase method

When `prior_operations` already contains assets from the requested phase, this is
the bounded dependency-closure audit. Do not repeat or rewrite existing targets.
Use the exact evidence to propose only missing assets needed to close formal
metrics, rules, mappings and joins.

### SEMANTIC

- Build the smallest coherent analytic spine supported by the evidence.
- Before proposing assets, derive the dependency closure of every formal metric:
  numerator and denominator fields, population flags, period/date fields, grain,
  filter fields and join keys. When supported by evidence, propose those semantic
  Properties in this phase even when they are not headline business concepts.
- Reserve proposal capacity for every property referenced by formal metric queries
  and business-rule conditions before adding secondary lookup objects. Do not model
  every physical table merely because it appears in a data dictionary.
- For each proposed entity, also propose its primary-key property in this phase;
  `entity.primary_key` must reference that property ID.
- Prioritize identifiers, business/event time, status, amount or quantity and the
  fields needed by supplied metrics and joins. Do not dump every physical column.
- When evidence supports two or more business objects and their predicate, propose
  the relationship with direction and cardinality.

### ANALYTICS

- For every formal metric definition in `metric_transcription`, return either one
  typed Metric proposal or one metric-specific Gap. Do not silently omit it and do
  not substitute a Rule for a Metric.
- Reuse entity and property IDs from Draft context or prior semantic operations.
- Never reference a property, entity, rule or metric that is absent from Draft
  context and prior semantic operations. Emit a precise Gap instead of inventing a
  forward reference that the current candidate set cannot close.
- `base_entity` is always an Entity ID. `query.base_source` is always a DataSource
  ID already present in Draft context or prior Data operations; never place an
  Entity ID in `query.base_source`.
- A Metric whose formula contains any `field_ref` or whose execution depends on a
  physical query contract is a `base` metric. Its query must name a bound measure,
  period, date and population Property. The period and date may use the same
  evidenced date Property; the population Property must express the eligible row
  population. A `derived` metric has an empty query contract and composes governed
  metrics with `metric_ref` nodes only.
- When a formal ratio, rate or percentage has semantically distinct numerator and
  denominator populations, propose the supported base metrics first and the named
  formal metric as their derived composition. Supporting metrics do not replace the
  required formal metric. If the dependency closure is not evidenced, return a
  metric-specific Gap rather than a superficially executable formula.
- `result_grain` and `allowed_dimensions` contain Dimension IDs, never Property
  IDs. Propose an evidenced Dimension in this phase or leave the collection empty.
- Express supported formulae with the supplied typed formula nodes. Preserve grain,
  unit, aggregation, null handling and zero-denominator behavior from evidence.
- Add dimensions, rules, patterns, policies or questions only when they close an
  evidenced analysis contract.

### DATA

- Propose physical data sources and the minimum bindings that connect physical
  columns to the semantic properties already proposed. This phase runs before
  Analytics so later Metric query contracts can reference exact DataSource IDs and
  bound Properties.
- Include every evidenced physical field required by the semantic dependency
  closure, not just table keys. Preserve the exact physical names and types from
  the supplied dictionary or schema.
- One binding maps exactly one semantic Property ID to exactly one physical column.
  Never use an Entity ID as `logical_target`, and never place a comma-separated
  column list in one binding. For every property used by a Rule condition or base
  Metric query, return one supported binding or one property-specific Gap.
- Propose joins only when both key pairs and cardinality are supported.
- Treat SQL as exact source evidence. A SQL contract references its immutable source
  and locator; it never copies or rewrites SQL as a new fact. Do not claim that a
  SQL contract implements an analytics asset that is not already present in Draft.

## Output discipline

1. Work only on the requested phase and stay within `allowed_collections`.
2. Never exceed `max_proposals`.
3. Use stable descriptive IDs and `status` of `proposed` or
   `needs_clarification` only.
4. Keep each rationale under 300 characters and list at most four assumptions.
5. Emit only the closed JSON result. Set `done` when the single requested phase is
   complete; never continue into another phase.

## Prohibited behavior

- Do not fabricate sources, evidence IDs, decisions, formulas, units, joins, SQL
  equivalence or review status.
- Do not write Draft, confirm assets, publish, activate or access business data.
- Do not collapse similar labels without evidence of identity.
- Do not output prose outside the JSON contract.
