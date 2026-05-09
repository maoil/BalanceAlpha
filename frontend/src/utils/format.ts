export function formatNumber(value: number | null | undefined, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "-";
  }
  return new Intl.NumberFormat("zh-CN", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
}

export function formatSignedNumber(value: number | null | undefined, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "-";
  }
  const prefix = value > 0 ? "+" : "";
  return `${prefix}${formatNumber(value, digits)}`;
}

export function formatPercent(value: number | null | undefined, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "-";
  }
  return `${formatNumber(value * 100, digits)}%`;
}

export function formatDate(value?: string | null) {
  if (!value) {
    return "-";
  }
  return value.slice(0, 10);
}

export function valueTone(value: number | null | undefined) {
  if (!value) {
    return "neutral";
  }
  return value > 0 ? "positive" : "negative";
}

export function compactJson(value: unknown) {
  if (value === null || value === undefined) {
    return "-";
  }
  if (typeof value === "string" || typeof value === "number") {
    return String(value);
  }
  return JSON.stringify(value, null, 2);
}
