import json

from evonext.contracts.trajectory import Snapshot, encode_json
from evonext.evaluation.inputs import InputOptions, prepare_input


def snapshot(created="2026-07-18 09:57:12", local="20260718095708127"):
    document = {
        "task_id": "synthetic-source-context", "instruction": "Look up five days earlier",
        "_version_info": {"version_number": 0}, "created_at": created,
        "metadata": {"evaluation": "must not enter", "backflow_raw": {
            "input_properties": [{"endpoint": json.dumps({
                "localTime": local, "timeZone": "+0800", "private_device_id": "do not expose",
            })}],
            "output_properties": [{"judge_answer": "must not enter"}],
        }},
        "traj": [{"index": 1, "step_type": "agent", "user_interrupt": "Use noon instead",
                  "runtime": {"current_time": "09:57:11.599", "effective": True,
                              "dispatched_action": {"action": "open", "text": "synthetic app"}},
                  "value": {"thought": "synthetic thought", "unknown": "keep in source"}}],
    }
    return Snapshot.create(encode_json(document))


def test_source_clock_amendment_role_and_dispatch_survive_a_readonly_view():
    source = snapshot()
    raw = source.trajectory_json
    preview = prepare_input(source, InputOptions(include_think=True))
    context = preview["model_context"]
    assert preview["profile"] == "evonext.evaluation-input.v3"
    anchor = context["source_context"]["task_date_anchor"]
    assert anchor["status"] == "corroborated_local_date"
    assert anchor["date"] == "2026-07-18"
    facts = context["steps"][0]["facts"]
    assert facts["step"]["user_interrupt"] == "Use noon instead"
    assert facts["step"]["step_type"] == "agent"
    assert facts["runtime"]["current_time"] == "09:57:11.599"
    assert facts["runtime"]["effective"] is True
    assert facts["runtime"]["dispatched_action"]["text"] == "synthetic app"
    assert "private_device_id" not in json.dumps(context)
    assert "judge_answer" not in json.dumps(context)
    assert "must not enter" not in json.dumps(context)
    assert source.trajectory_json == raw
    assert context["steps"][0]["fact_refs"]["runtime"]["dispatched_action"].endswith(
        "/steps/0/facts/runtime/dispatched_action")
    assert context["steps"][0]["observation_relation"]["next_recorded_image"] is None


def test_clock_conflict_never_becomes_a_date_anchor():
    source = snapshot(local="20260719095708127")
    context = prepare_input(source, InputOptions())["model_context"]["source_context"]
    assert context["task_date_anchor"] == {"status": "conflicting"}
    assert context["clocks"][1]["value"] == "20260719095708127"


def test_timezone_is_applied_to_an_aware_created_timestamp():
    source = snapshot(created="2026-07-17T17:57:12+00:00")
    anchor = prepare_input(source, InputOptions())["model_context"]["source_context"]["task_date_anchor"]
    assert anchor["date"] == "2026-07-18"


def test_unstructured_effective_and_invalid_clock_stay_in_original_only():
    source = snapshot()
    document = source.document
    document["created_at"] = {"evaluation": "hidden"}
    document["traj"][0]["runtime"]["effective"] = {"judge_answer": "hidden"}
    source = Snapshot.create(encode_json(document))
    preview = prepare_input(source, InputOptions())
    assert "effective" not in preview["model_context"]["steps"][0]["facts"]["runtime"]
    assert preview["model_context"]["source_context"]["task_date_anchor"]["status"] == "unknown"
    assert source.document["created_at"] == {"evaluation": "hidden"}
