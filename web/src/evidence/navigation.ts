export function navigationTarget(
  key: string,
  index: number,
  count: number,
  columns: number,
  grid: boolean,
) {
  if (!count) return 0;
  if (key === "Home") return 0;
  if (key === "End") return count - 1;
  if (key === "ArrowLeft") return (index - 1 + count) % count;
  if (key === "ArrowRight") return (index + 1) % count;
  if (grid && key === "ArrowUp")
    return index - columns >= 0 ? index - columns : index;
  if (grid && key === "ArrowDown")
    return index + columns < count ? index + columns : index;
  return index;
}
