# Domain-neutral modeling rules

- An entity is a business thing or event at one declared grain and lifecycle.
- A property belongs to exactly one entity and has a closed data type. An entity's
  primary key references a property ID, not a physical column name by convention.
- A relationship declares a business predicate, direction and cardinality.
- A metric declares a base entity, result grain, value type, unit, aggregation,
  typed formula and query contract. A textual formula alone is not executable.
- Base metrics own physical query contracts and may reference bound fields.
  Derived metrics own no physical query contract and compose governed metrics.
- A ratio or percentage normally requires separately governed numerator and
  denominator base metrics before the named derived metric can close.
- `Metric.base_entity` references an Entity; `Metric.query.base_source` references
  a DataSource; metric grain and allowed dimensions reference Dimension objects.
- A rule separates population eligibility, data quality and policy restrictions.
- A data contract separates logical semantics from physical sources and mappings.
- A binding connects one logical target to one physical source/table/column.
- A join declares both sources, key pairs, cardinality and fan-out policy.
- A SQL contract points to immutable SQL evidence and declares inputs, outputs,
  parameters, dialect and governed assets implemented. It never duplicates mutable
  SQL text, and SQL evidence alone does not prove business equivalence.
- Analysis questions point to supported analysis contracts; they do not replace
  metric definitions.
- Every governed asset cites registered sources. Assumptions remain explicit and
  require human disposition.
