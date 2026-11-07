import "./tags.css";
// The original tag-chip markup, without the old catalogue/editor/network controller.
export function ReadOnlyTags({ tags }: { tags: string[] }) {
  return (
    <div className="fw-tags" aria-label="来源任务标签">
      <div className="fw-tag-rail">
        <div className="fw-tag-chips">
          {tags.length ? (
            tags.map((tag) => (
              <span className="fw-tag-chip" key={tag.toLowerCase()} title={tag}>
                <span className="fw-tag-name">{tag}</span>
              </span>
            ))
          ) : (
            <span className="fw-tag-empty">未携带</span>
          )}
        </div>
      </div>
    </div>
  );
}
