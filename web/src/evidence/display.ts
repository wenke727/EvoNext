export const evidenceJson = (value: unknown) => JSON.stringify(value ?? null, null, 2);
export const evidenceText = (value: unknown) =>
  value == null
    ? "未记录"
    : typeof value === "string"
      ? value
      : JSON.stringify(value);
