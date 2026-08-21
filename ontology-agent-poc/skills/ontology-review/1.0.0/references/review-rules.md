# Review rules

- Evidence support is claim-specific. A source being present is not enough.
- A model-inferred Candidate without a usable evidence anchor is unsupported.
- Two operations targeting the same collection and object require merge resolution.
- Source, decision, entity, property, metric, mapping and Join references must exist
  in the Draft or in the same candidate set.
- Formula, unit, grain, time semantics, filters, cancellation handling and Join
  cardinality must agree across semantic and data contracts.
- A no-change Candidate is not automatically wrong, but should not be applied as a
  new change without an explicit reason.
- Findings never confer human authority.
