const canonicalDecimal = /^-?(?:0|[1-9]\d*)(?:\.\d+)?$/;

const displayNumber = new Intl.NumberFormat("en-US", {
  maximumFractionDigits: 2,
  useGrouping: true,
});


export function formatDisplayValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "number") {
    return Number.isFinite(value) ? displayNumber.format(value) : String(value);
  }
  if (typeof value !== "string" || !canonicalDecimal.test(value)) {
    return String(value);
  }
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || Math.abs(parsed) > Number.MAX_SAFE_INTEGER) {
    return value;
  }
  return displayNumber.format(parsed);
}
