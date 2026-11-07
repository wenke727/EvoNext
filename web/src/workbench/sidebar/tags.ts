export function uniqueTags(value: unknown): string[] {
  const seen = new Set<string>();
  return (Array.isArray(value) ? value : [])
    .filter((tag): tag is string => typeof tag === "string")
    .map((tag) => tag.trim())
    .filter((tag) => {
      const key = tag.toLowerCase();
      if (!tag || seen.has(key)) return false;
      seen.add(key);
      return true;
    });
}
