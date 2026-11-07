import { test } from "node:test";
import assert from "node:assert/strict";
import {
  projectEvaluation,
  resultBinding,
} from "../src/evidence/evaluation.ts";
import { trajectorySignals } from "../src/evidence/legend.ts";

const taskId = "922337203685477580700012345678901";
const detail = (evaluation) => ({
  snapshot_id: "a".repeat(64),
  task_id: taskId,
  source_version: 0,
  missing_media: [],
  trajectory: {
    task_id: taskId,
    traj: [
      { index: 7, image: "a.png", value: {} },
      { index: 9, image: "b.png", value: {} },
    ],
    ...(evaluation === undefined ? {} : { evaluation }),
  },
  metadata: {},
});
const source = { source_task_id: taskId, source_version: 0 };

test("an offline package without evaluations does not imply not-assessed or failure", () => {
  const view = projectEvaluation(detail());
  assert.equal(view.carried, false);
  assert.equal(view.machine.carried, false);
  assert.deepEqual(view.graders, []);
  assert.deepEqual(view.machine.statuses, []);
});
test("source version zero is retained; matching source version remains distinct from exact snapshot binding", () => {
  assert.equal(resultBinding(source, detail()).relation, "version");
  assert.equal(
    resultBinding({ ...source, source_snapshot_id: "a".repeat(64) }, detail())
      .relation,
    "snapshot",
  );
  assert.equal(
    resultBinding({ ...source, source_version: 1 }, detail()).relation,
    "other_version",
  );
  assert.equal(
    resultBinding({ ...source, source_version: "0" }, detail()).relation,
    "unknown",
  );
  assert.equal(
    resultBinding(
      {
        ...source,
        source_task_id: "other",
        source_snapshot_id: "a".repeat(64),
      },
      detail(),
    ).relation,
    "other_task",
  );
});
test("reference navigation resolves source indices to positions and never treats index as ordinal", () => {
  const input = detail({
    graders: [
      { key: "x", ...source, items: [{ status: false, step_indices: [9, 1] }] },
    ],
  });
  const view = projectEvaluation(input);
  assert.equal(view.graders[0].items[0].references[0].position, 1);
  assert.match(view.graders[0].items[0].references[0].label, /来源参考/);
  assert.equal(view.graders[0].items[0].references[1].position, null);
});
test("other-task or other-version evaluations cannot navigate into the current evidence", () => {
  for (const mismatch of [
    { source_task_id: "other" },
    { source_version: 1 },
    { source_snapshot_id: "b".repeat(64) },
  ]) {
    const view = projectEvaluation(
      detail({
        graders: [
          {
            key: "x",
            ...source,
            ...mismatch,
            items: [{ status: false, step_indices: [7] }],
          },
        ],
      }),
    );
    assert.equal(view.graders[0].items[0].references[0].position, null);
  }
});
test("duplicate step identities cannot silently pick one position", () => {
  const input = detail({
    graders: [{ key: "x", ...source, items: [{ step_indices: [7] }] }],
  });
  input.trajectory.traj[1].index = 7;
  assert.equal(
    projectEvaluation(input).graders[0].items[0].references[0].position,
    null,
  );
});
test("false, null, true and missing/invalid judgments keep separate meanings and the full denominator", () => {
  const input = detail({
    graders: [
      {
        key: "x",
        ...source,
        items: [
          { status: false },
          { status: null },
          { status: true },
          { status: "false" },
          {},
        ],
      },
    ],
  });
  const statuses = projectEvaluation(input).graders[0].items.map(
    (item) => item.status,
  );
  assert.deepEqual(statuses, [false, null, true, undefined, undefined]);
});
test("evaluation reads preserve unknown fields, repeated grader keys and malformed source payloads", () => {
  const input = detail({
    unknown: { keep: 0 },
    graders: [
      {
        key: "same",
        ...source,
        extra: 42,
        items: [{ status: false, unknown: [1, 2] }],
      },
      { key: "same", ...source, summary: "another result" },
    ],
  });
  const before = JSON.stringify(input);
  const view = projectEvaluation(input);
  assert.equal(view.graders.length, 2);
  assert.deepEqual(view.raw.unknown, { keep: 0 });
  assert.equal(view.graders[0].raw.extra, 42);
  assert.equal(JSON.stringify(input), before);
  assert.equal(
    projectEvaluation(detail("unrecognized source")).raw,
    "unrecognized source",
  );
});
test("dynamic legends distinguish source judgment, proposal, actual receipt and missing media", () => {
  const input = detail();
  input.trajectory.traj = [
    {
      image: "a.png",
      value: { last_step_correct: true, rejected_model_outputs: ["retry"] },
    },
    {
      image: null,
      value: {
        error_reason: "recorded error",
        execution_result: { status: "success" },
      },
      user_interrupt: "follow-up",
      step_type: "human",
    },
    {
      image: "b.png",
      value: {
        tool_call: { name: "mobile_use", arguments: { action: "take_over" } },
      },
    },
  ];
  const result = trajectorySignals(input);
  assert.ok(result.legend.includes("current"));
  assert.ok(result.legend.includes("sourceCorrect"));
  assert.ok(result.legend.includes("sourceError"));
  assert.ok(result.legend.includes("modelRetry"));
  assert.ok(result.legend.includes("missing"));
  assert.ok(result.legend.includes("human"));
  assert.ok(result.legend.includes("followup"));
  assert.ok(result.legend.includes("takeoverProposal"));
  assert.equal(result.steps[1].includes("sourceCorrect"), false);
  assert.equal(result.steps[2].includes("takeover"), false);
});
test("multiple terminate proposals are marked without becoming failures or approvals", () => {
  const input = detail();
  input.trajectory.traj = [0, 1].map((index) => ({
    index,
    image: "a.png",
    value: {
      tool_call: {
        name: "mobile_use",
        arguments: { action: "terminate", status: "success" },
      },
    },
  }));
  const result = trajectorySignals(input);
  assert.ok(result.legend.includes("multiEnd"));
  assert.equal(result.legend.includes("sourceCorrect"), false);
  assert.equal(result.legend.includes("sourceError"), false);
});

test("the migrated original view receives v0, source references and distinct missing judgments without changing evidence", async () => {
  const { adaptEvaluationView } = await import(
    "../src/evidence/evaluation-view.ts"
  );
  const input = detail({
    prediction: { ...source, task_status: ["failed"] },
    graders: [
      {
        key: "x",
        ...source,
        items: [{ status: false, step_indices: [9] }, { status: null }, {}],
      },
    ],
  });
  const before = JSON.stringify(input);
  const view = adaptEvaluationView(input);
  assert.equal(view.version, "0");
  assert.equal(view.machine.source.inputVersion, 0);
  assert.equal(view.machine.source.relation, "same_version");
  assert.deepEqual(view.knownSteps, [0, 1]);
  assert.equal(view.graders[0].scope, "unknown");
  assert.equal(view.graders[0].items[0].references[0].position, 1);
  assert.deepEqual(
    view.graders[0].items.map((item) => item.status),
    [false, null, undefined],
  );
  assert.equal(JSON.stringify(input), before);
});

test("migrated raw-result formatting does not unescape literal source characters", async () => {
  const { text, hasValue } = await import(
    "../src/workbench/evaluation/contracts.ts"
  );
  assert.equal(text("literal\\nsource"), "literal\\nsource");
  assert.equal(hasValue(0), true);
  assert.equal(hasValue(false), true);
});
