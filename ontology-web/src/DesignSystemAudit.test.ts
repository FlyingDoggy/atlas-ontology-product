import { describe, expect, it } from "vitest";
// The production bundle intentionally has no Node runtime dependency. Vitest
// runs this source audit in Node, so keep the one built-in import local here.
// @ts-expect-error Node typings are deliberately not part of the browser tsconfig.
import { readFileSync } from "node:fs";

const stylesheet = readFileSync("src/styles.css", "utf8");

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
});
