# Ontology Products — EIX Design System Audit

## Audit baseline

The previous stylesheet contained 747 type declarations. More than 300 visible declarations rendered at 7–11px. Browser sampling confirmed that this was systemic rather than page-specific: the solution directory, Studio overview, authoring pages, shared shell, and Analytic Agent all rendered visible text below the EIX 12px floor.

## Enforced typography contract

| Role | Token | Size | Typical use |
| --- | --- | ---: | --- |
| Metadata | `--semantic-type-meta` | 12px | IDs, timestamps, eyebrow labels, table headers, technical annotations |
| Control | `--semantic-type-control` | 14px | Buttons, fields, tabs, navigation support text, compact prose |
| Supporting | `--semantic-type-supporting` | 15px | List titles, navigation labels, card titles |
| Body | `--semantic-type-body` | 17px | Reading text and result narratives |
| Lead | `--semantic-type-lead` | 19px | Section introductions and prominent labels |
| Heading S/M/L | component tokens | 22/26/32px | Card, workbench, and page headings |
| Display | component token | 44px | Product/directory hero only |

No normal visible text may render below 12px. Density must come from spacing, grouping, progressive disclosure, and scroll—not unreadably small type.

## UI rules applied globally

- The shared shell uses EIX semantic font, color, spacing, radius, elevation, and focus tokens.
- Chinese content falls back to `PingFang SC` / `Microsoft YaHei`; utility identities and code use the EIX utility stack.
- Page titles, section titles, list titles, body copy, controls, and metadata have distinct semantic roles.
- Content selection uses surface/background contrast. A leading accent rail is reserved for primary navigation or workflow state, not repeated master-detail rows.
- Controls use a 44px default target; compact secondary controls may use 36px where the surrounding table or toolbar establishes the context.
- Raised elevation is reserved for overlays and drawers. Normal workbench sections remain flat and separated by borders/surfaces.

## Regression guard

`DesignSystemAudit.test.ts` fails if a future change introduces text below 12px or arbitrary off-scale literal font sizes. Browser-level rendered audits remain part of release QA because CSS declarations alone cannot detect every cascade and responsive-layout issue.

## Post-remediation verification (2026-08-22)

- 19 product routes were sampled in the deployed local Docker build: directory, overview, every Studio workbench, governance/release pages, and the Analytic Agent.
- Normal visible text below 12px: **0**. The review queue retains an intentional `font-size: 0` on a wrapper whose visible select control renders at 14px.
- Page-level horizontal overflow at a 1280px viewport: **0 routes**. Internal tables/canvases may scroll or ellipsize by design.
- Shared computed roles were verified in-browser: body 14px, page title 32px, navigation title 15px, supporting card title 15px, metadata 12px.
- Typecheck, 78 unit/component tests, production build, and Docker rebuild passed.

## Remaining non-blocking design-system debt

Typography is now governed and the major page hierarchy/layout is aligned. The legacy stylesheet still contains many component-local hexadecimal colors and raw spacing values. They are visually constrained by the EIX semantic foundations and final role layer, but they are not yet 100% token-pure. Therefore the correct claim is **EIX-aligned product UI**, not “every historical declaration is an EIX token.” A later maintainability refactor should split the monolithic stylesheet by shell/component and migrate those local values without changing the validated product behaviour.
