import { useState } from "react";
import type { Detail } from "./client";
import { Panel } from "../workbench/evaluation/Panel";
import { initialState } from "../workbench/evaluation/contracts";
import { adaptEvaluationView } from "./evaluation-view";

// The migrated view stays source-shaped; only this adapter knows EvoNext snapshots and navigation.
export function EvaluationPanel({
  detail,
  onStep,
  embedded = false,
}: {
  detail: Detail;
  position: number;
  embedded?: boolean;
  onStep: (position: number) => void;
}) {
  const [state, setState] = useState(initialState);
  const view = adaptEvaluationView(detail);
  return (
    <section
      className={
        embedded ? "source-evaluation" : "task-section source-evaluation"
      }
      aria-label="评估结果"
    >
      {!embedded && <h2>评估</h2>}
      <Panel
        view={view}
        state={state}
        onState={setState}
        onStep={(event, index) => {
          event.preventDefault();
          onStep(index);
        }}
      />
      <p className="evaluation-footnote">
        只读来源结果；浏览不会运行 ORM 或 grader。
      </p>
    </section>
  );
}
