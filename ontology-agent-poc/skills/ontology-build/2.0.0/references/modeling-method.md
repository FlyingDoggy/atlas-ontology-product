# Evidence-to-Ontology Modeling Method

Trace each business obligation through the smallest coherent chain needed to make it
usable and reviewable:

1. business requirement or question;
2. governed object, rule, metric, or process;
3. properties and relationships required by that meaning;
4. grain, unit, time basis, population and exclusions;
5. physical source, field binding, joins, SQL contract and boundary behavior;
6. claim-level Evidence Receipts or an explicit Gap.

Prefer explicit missingness over invented completeness. A Candidate may temporarily
contain unresolved references while exploring, but completion requires deterministic
closure. Keep source codes, physical identifiers, formulas and SQL exact; translate
only human-readable ontology content into the selected output language.

For analytical rates, separate meaning from arithmetic. The numerator and denominator
are governed base metrics with distinct population/filter semantics and physical
lineage. The reported rate is a derived metric that composes those metric identities.
For SQL-derived values, bind only to the exact derived relation and named output proven
by the SQL evidence. Do not invent a convenient raw column or substitute an additive
aggregation for a percentile or distribution contract. When the governed formula DSL
models one observation, represent a distribution requirement with a base observation
Metric plus an Analysis Pattern for the requested quantiles/profile and an exact SQL
Contract for executable lineage. The absence of a percentile operator in an additive
formula DSL is not by itself an ontology Gap.

The `sources` array is a provenance summary, not a reading list. Every source newly
declared there must appear in at least one claim's server-minted Evidence Receipt. If a
source only supports an interpretation, cite it with `INFERRED`; never list a source
without a receipt or attach one receipt from a different document to a multi-source
claim.

After existing candidates have cited and evidenced a frozen source, close its coverage
obligation with `obligation.cover`. A Gap represents missing meaning or unsupported
processing, not the absence of a second duplicate Candidate.

Sample data has a different authority role from a requirement or metric document, but
it is still evidence. Read representative exact ranges and use them to support physical
shape, observed value domains, enum candidates, nullability/quality observations or
executable test fixtures. Lack of normative business prose is not a reason to mark a
parseable sample-data source as a Gap; it only limits which claims the rows may support.
