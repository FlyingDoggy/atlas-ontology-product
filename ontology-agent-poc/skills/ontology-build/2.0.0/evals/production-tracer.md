# Production Tracer Eval

Given a short anonymous service-request requirement, the Builder must:

- discover and read exact evidence;
- create an entity whose primary-key property is initially absent;
- receive a deterministic closure failure;
- add the missing property;
- request completion again and produce a sealed review-ready Candidate Bundle;
- never write Draft, ReviewDecision, Release, or Active state.

Additional invariant cases:

- a rate with physical aggregation inside a derived formula must fail until it is
  decomposed into evidenced base numerator/denominator metrics plus metric references;
- division by an identical expression must fail as a tautology;
- a SQL-derived field must resolve to an evidenced derived relation/output and may not
  be invented in a physical table;
- an already-evidenced Candidate may close source coverage through
  `obligation.cover`; a Candidate that cites a different logical source or lacks an
  exact receipt may not;
- sample data must be inspected for validation/evaluation relevance rather than
  automatically dispositioned as unnecessary.
