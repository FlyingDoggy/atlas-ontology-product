# Cash Trading Demo Execution Baseline v1

Status: Approved on 2026-08-24

## North star

Deliver one credible demonstration path:

`Build entry → prebuilt Cash Trading Ontology Package → Studio inspection and graph → DeepAgent analysis → answer with data and evidence`

The Studio manages and explains a versioned Ontology Package. The Analytic Agent consumes that Package. The LLM may interpret, plan, explore and explain; the Package governs business semantics and mappings; the query engine performs deterministic computation; evidence makes every answer inspectable.

## Product guidance

- Cash Trading is a complete demo case, not product-level hard-coded behavior.
- The prebuilt Package is the primary deliverable; every screen serves its inspection or consumption.
- The Build entry demonstrates the future upload flow but does not run document processing in this release.
- Studio prioritizes comprehension of the Package over workflow breadth.
- Agent prioritizes correct domain answers over displaying agent internals.
- Unconfirmed Deloitte interpretations remain explicit assumptions, never confirmed HKEX facts.

## Technical guidance

- A single Package Contract is authoritative for Studio and Agent.
- Studio renders Package data generically; it contains no Cash Trading-specific page logic.
- DeepAgent exposes only the minimum tools needed to inspect ontology, query data and retrieve evidence.
- Answers are not hard-coded or selected through question-keyword routing.
- Synthetic data is stored separately from the semantic Package.
- Local verification precedes any EC2 deployment.

## UI guidance

- Apply the EIX design-system foundations consistently.
- Use a restrained enterprise configuration-product layout for Studio.
- Use the original lightweight HTML agent and the Audi PoC interaction model as references for the Agent.
- Standard desktop at 100% browser zoom is the visual acceptance baseline.
- Prefer navigation, tables, details and graphs over explanatory hero sections.

## Delivery slices

1. Freeze source evidence, assumptions and the shared Package Contract.
2. Build and validate the versioned Cash Trading Ontology Package offline.
3. Deliver Studio overview, catalogs, asset details, mappings and three graph views.
4. Deliver the guided Build entry and prepared demo upload materials without backend processing.
5. Deliver a lightweight DeepAgent runtime and simple Agent UI bound to the active Package.
6. Establish Golden Questions with exact answers, calculations and evidence.
7. Complete local browser integration testing and the demo manual.

## Minimum Package coverage

- 8 business entities
- 8 core relationships
- 8 business metrics
- 8 analytical dimensions
- At least 39 canonical attribute-to-field mappings
- Rules, enumerations, joins, transformations, lineage, sources, assumptions and gaps

## Explicit exclusions

- Repairing or completing the generic automatic Builder pipeline
- A production task center or broad governance workflow
- Enterprise IAM, approval, source-system integration or Knowledge Center architecture
- Additional orchestrator, reviewer or policy agents
- EC2 deployment before local approval

## Acceptance rule

A slice is complete only when its data comes from the same Package, its visible workflow works in a browser, and it has reproducible test evidence. Code completion alone is not acceptance.
