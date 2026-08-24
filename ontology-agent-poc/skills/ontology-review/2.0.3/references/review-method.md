# Independent Review Method

Review the sealed denominator, not a convenient sample. The server-owned execution
plan supplies the exact list pages and high-risk batches; use them as routing, not as a
substitute for judgment. First ask whether the Bundle contains the right kinds of
artifacts to represent the business request. Then ask whether each artifact is correct.

For every analytical requirement, independently trace:

1. Requirement to Question and expected answer;
2. Question to Analysis Pattern and allowed dimensions/policies;
3. Pattern to governed Metric, Rule, Object, Relationship, and Process;
4. semantic contract to Property, Binding, Join, Data Source, and SQL;
5. every material claim to exact evidence or an explicit Gap.

The frozen `required_candidate_collections` values are minimum type requirements, not
proof of quality. Verify both presence and meaningful connectivity. A Metric cannot
substitute for a Question, a Question cannot substitute for an Analysis Pattern, and
a Binding cannot substitute for a Join.

For metrics, construct an independent semantic ledger covering expected output unit,
currency and scale; operand units; formula scaling; filters; population; denominator
behavior; and SQL output. Test currency relabeling, absent FX conversion, missing or
double millions/percentage factors, raw-ratio drift, and formula/SQL disagreement.

Group repeated defect patterns into one finding. Do not repeat deterministic findings
unless exact evidence expands their scope. If evidence is insufficient, describe the
uncertainty precisely. Advisory severity does not grant release authority.
