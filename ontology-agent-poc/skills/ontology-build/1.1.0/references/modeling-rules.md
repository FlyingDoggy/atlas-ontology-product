# Domain-neutral modeling rules

- An object represents a business thing at a declared grain and lifecycle.
- A property belongs to exactly one object and has a closed data type.
- A relationship names a business predicate and declares direction and cardinality.
- A metric declares a base object, result grain, value type, unit, aggregation
  semantics and a typed formula. A textual formula alone is not executable.
- A rule separates population eligibility, data quality and policy restrictions.
- A data contract separates logical semantics from physical sources and mappings.
- A join identifies both sources, key pairs, expected cardinality and fan-out policy.
- A SQL contract points to an immutable SQL source and locator, declares physical
  inputs, outputs, parameters, dialect and the governed metrics/rules/patterns it
  implements. The contract never duplicates mutable SQL text.
- Executable SQL contracts are read-only and require declared inputs, outputs and an
  implemented governed asset. SQL evidence does not prove business equivalence.
- Analysis questions point to supported analysis contracts; they are not a substitute
  for metric definitions.
- Every governed asset cites registered sources. Assumptions are explicit and require
  later human disposition.
- Similar labels do not prove concepts are identical. Propose duplicate or merge
  review instead of silently collapsing them.
