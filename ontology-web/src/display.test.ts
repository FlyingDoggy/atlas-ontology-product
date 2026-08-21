import { describe, expect, it } from "vitest";

import { formatDisplayValue } from "./display";


describe("formatDisplayValue", () => {
  it("formats package numeric scalars without leaking storage precision", () => {
    expect(formatDisplayValue("8210000.000000")).toBe("8,210,000");
    expect(formatDisplayValue("-19825.6570387717928701535259")).toBe("-19,825.66");
    expect(formatDisplayValue(10)).toBe("10");
  });

  it("preserves identifiers, periods and leading-zero values", () => {
    expect(formatDisplayValue("2025-Q3")).toBe("2025-Q3");
    expect(formatDisplayValue("PART001")).toBe("PART001");
    expect(formatDisplayValue("001")).toBe("001");
  });

  it("renders missing values consistently", () => {
    expect(formatDisplayValue(null)).toBe("—");
    expect(formatDisplayValue(undefined)).toBe("—");
  });
});
