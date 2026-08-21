import { describe, expect, it } from "vitest";
// The production bundle intentionally has no Node runtime dependency. Vitest
// runs this source audit in Node, so keep the one built-in import local here.
// @ts-expect-error Node typings are deliberately not part of the browser tsconfig.
import { readFileSync } from "node:fs";

const stylesheet = readFileSync("src/styles.css", "utf8");
const sourceLibrary = readFileSync("src/StudioProductViews.tsx", "utf8");
const construction = readFileSync("src/StudioConstructionViews.tsx", "utf8");

describe("EIX design-system contract", () => {
  it("keeps the EIX readable type floor at 12px", () => {
    const undersizedFontSizes = [
      ...stylesheet.matchAll(/font-size:\s*(\d+(?:\.\d+)?)px/g),
    ]
      .map((match) => Number(match[1]))
      .filter((size) => size > 0 && size < 12);

    const undersizedFontShorthands = [
      ...stylesheet.matchAll(/font:\s*[^;\n]*?\s(\d+(?:\.\d+)?)px\//g),
    ]
      .map((match) => Number(match[1]))
      .filter((size) => size > 0 && size < 12);

    expect(undersizedFontSizes).toEqual([]);
    expect(undersizedFontShorthands).toEqual([]);
  });

  it("defines and uses the shared EIX semantic typography roles", () => {
    expect(stylesheet).toContain("--semantic-type-meta: 12px");
    expect(stylesheet).toContain("--semantic-type-control: 14px");
    expect(stylesheet).toContain("--semantic-type-supporting: 15px");
    expect(stylesheet).toContain("--semantic-type-body: 17px");
    expect(stylesheet).toContain("--semantic-type-lead: 19px");
    expect(stylesheet).toContain("font-family: var(--semantic-font-body)");
    expect(stylesheet).toContain("h1, h2, h3, h4, h5, h6 { font-family: var(--semantic-font-heading); }");
  });

  it("does not reintroduce arbitrary off-scale text sizes", () => {
    const allowedLiteralSizes = new Set([0, 12, 14, 15, 17, 19]);
    const literalSizes = [
      ...stylesheet.matchAll(/font-size:\s*(\d+(?:\.\d+)?)px/g),
      ...stylesheet.matchAll(/font:\s*[^;\n]*?\s(\d+(?:\.\d+)?)px\//g),
    ].map((match) => Number(match[1]));

    expect(literalSizes.filter((size) => !allowedLiteralSizes.has(size))).toEqual([]);
  });

  it("uses the full workspace width and a shared alignment edge", () => {
    expect(stylesheet).toMatch(/\.studio-page-header,\s*\.role-gated-content\.studio-page-content\s*\{[\s\S]*?width:\s*100%;[\s\S]*?max-width:\s*none;[\s\S]*?margin-inline:\s*0;/);
  });

  it("uses a whole-row source preview affordance instead of a narrow action column", () => {
    expect(sourceLibrary).toContain('className="source-library-row"');
    expect(sourceLibrary).toContain('aria-label={`查看 ${source.title} 详情`}');
    expect(sourceLibrary).not.toContain('>查看详情</button>');
  });

  it("keeps scenario-specific language out of reusable source and construction components", () => {
    expect(sourceLibrary).not.toContain("Cash Trading 参考材料包");
    expect(sourceLibrary).not.toContain("Deloitte HK 提供");
    expect(construction).not.toContain("当前案例");
    expect(construction).not.toContain("fixed source set");
    expect(construction).not.toContain("Not installed");
  });
});
