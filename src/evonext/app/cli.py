import argparse
import json
from pathlib import Path

from evonext.config import Settings


def main():
    parser = argparse.ArgumentParser(prog="evonext")
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve")
    serve.add_argument("--demo", action="store_true")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    inspect_source = commands.add_parser("inspect-source", help="Read old source without persisting it")
    inspect_source.add_argument("--env-file", type=Path, required=True)
    inspect_source.add_argument("--task-id")
    inspect_source.add_argument("--version", type=int)
    inspect_source.add_argument("--limit", type=int, default=30)
    validate = commands.add_parser("validate-bundle")
    validate.add_argument("path", type=Path)
    evaluation_input = commands.add_parser("prepare-evaluation", help="Preview complete trajectory evaluation input")
    evaluation_input.add_argument("path", type=Path, help="Platform trajectory JSON or portable ZIP")
    evaluation_input.add_argument("--images", choices=["auto", "all", "last_three"], default="auto")
    evaluation_input.add_argument("--include-think", action="store_true")
    evaluation_input.add_argument("--max-images", type=int, default=10)
    evaluate = commands.add_parser("evaluate", help="Run a registered snapshot through Fast Judge")
    evaluate.add_argument("snapshot_id")
    evaluate.add_argument("--operation-id", required=True)
    evaluate.add_argument("--investigation", choices=["off", "auto", "always"], default="auto")
    evaluate.add_argument("--review-localization", action="store_true")
    evaluate.add_argument("--bind-decisions", action="store_true")
    replay = commands.add_parser("replay-evaluation", help="Offline synthetic judge response replay")
    replay.add_argument("path", type=Path)
    replay.add_argument("--responses", type=Path, required=True)
    replay.add_argument("--investigation", choices=["off", "auto", "always"], default="auto")
    replay.add_argument("--review-localization", action="store_true")
    replay.add_argument("--bind-decisions", action="store_true")
    enqueue = commands.add_parser("enqueue-integrity")
    enqueue.add_argument("snapshot_id")
    probe = commands.add_parser("model-probe")
    probe.add_argument("--text", required=True)
    workshop = commands.add_parser("workshop")
    workshop.add_argument("action", choices=["save", "show", "history", "diff", "restore", "archive", "export"])
    workshop.add_argument("skill_id")
    workshop.add_argument("--root", type=Path, required=True)
    workshop.add_argument("--owner", required=True)
    workshop.add_argument("--file", type=Path)
    workshop.add_argument("--expected")
    workshop.add_argument("--revision")
    workshop.add_argument("--source", action="append", default=[])
    workshop.add_argument("--reason", default="manual candidate revision")
    workshop_api = commands.add_parser("workshop-api", help="Draft/review/author through configured API")
    workshop_api.add_argument("action", choices=["list", "draft", "show", "review", "commit",
                                               "discard", "preview", "author", "status"])
    workshop_api.add_argument("--id", help="Draft hash or stable authoring operation ID")
    workshop_api.add_argument("--file", type=Path, help="Exact JSON request; reuse on recovery")
    workshop_api.add_argument("--url", default="http://127.0.0.1:8000")
    available = commands.add_parser("list-available", help="Filter a resource owner inventory JSON file")
    available.add_argument("--inventory", required=True, type=Path)
    available.add_argument("--driver", choices=["external_agent", "builtin_agent", "cloud_query"])
    available.add_argument("--capability", action="append", default=[])
    available.add_argument("--resource-id")
    prepare = commands.add_parser("prepare-trial")
    prepare.add_argument("--request", type=Path, required=True)
    prepare.add_argument("--bundle", type=Path, required=True)
    probe.add_argument("--operation-id", required=True)
    case = commands.add_parser("case")
    case.add_argument("action", choices=["show", "draft", "save", "review", "preview"])
    case.add_argument("case_id")
    case.add_argument("--url", default="http://127.0.0.1:8000")
    case.add_argument("--file", type=Path, help="Exact DraftCommand or FrozenReviewCommand JSON")
    case.add_argument("--revision", type=int)
    case.add_argument("--purpose", choices=["diagnosis", "localization", "sft", "dpo"])
    args = parser.parse_args()
    if args.command == "workshop-api":
        import httpx
        from urllib.parse import quote
        from evonext.config import secret
        paths = {"list": "", "draft": "/drafts", "show": "/drafts/{id}",
                 "review": "/drafts/{id}/review", "commit": "/drafts/{id}/commit",
                 "discard": "/drafts/{id}/discard", "preview": "/preview",
                 "author": "/operations", "status": "/operations/{id}"}
        path = paths[args.action]
        if "{id}" in path and not args.id:
            parser.error("--id is required")
        payload = None
        if args.action in {"draft", "review", "preview", "author"}:
            if not args.file:
                parser.error("--file is required")
            payload = json.loads(args.file.read_text(encoding="utf-8"))
        method = "GET" if args.action in {"list", "show", "status"} else "POST"
        with httpx.Client(base_url=args.url, headers={"X-API-Key": secret(Settings().api_key)},
                          timeout=60) as client:
            response = client.request(method, "/api/v1/workshop" +
                path.format(id=quote(args.id or "", safe="")), json=payload)
            if response.is_error:
                parser.exit(1, f"HTTP {response.status_code}: {response.text}\n")
            print(json.dumps(response.json(), ensure_ascii=False, indent=2))
    elif args.command == "case":
        import httpx
        from uuid import UUID
        from evonext.config import secret
        from evonext.review.corrections import DraftCommand, FrozenReviewCommand
        UUID(args.case_id)
        settings = Settings()
        path = f"/api/v1/cases/{args.case_id}"
        headers = {"X-API-Key": secret(settings.api_key)}
        method, payload = "GET", None
        if args.action == "draft":
            path += "/draft"
        elif args.action in {"save", "review"}:
            if not args.file:
                parser.error("--file is required for a mutation; reuse it to retry the same command")
            command_type = DraftCommand if args.action == "save" else FrozenReviewCommand
            command = command_type.model_validate_json(args.file.read_text())
            payload = command.model_dump(mode="json")
            revision = (command.expected_draft_revision if isinstance(command, DraftCommand)
                        else command.expected_review_revision)
            headers["If-Match"] = f'"{revision}"'
            method = "PUT" if args.action == "save" else "POST"
            path += "/draft" if args.action == "save" else "/review"
        elif args.action == "preview":
            if args.revision is None or not args.purpose:
                parser.error("--revision and --purpose are required")
            path += f"/reviews/{args.revision}/previews/{args.purpose}"
        with httpx.Client(base_url=args.url, headers=headers, timeout=30) as client:
            response = client.request(method, path, json=payload)
            if response.is_error:
                parser.exit(1, f"HTTP {response.status_code}: {response.text}\n")
            print(json.dumps(response.json(), ensure_ascii=False, indent=2))
    elif args.command == "serve":
        import uvicorn
        from evonext.app.api import create_app
        settings = Settings(demo=True) if args.demo else Settings()
        if settings.demo and args.host not in {"127.0.0.1", "::1", "localhost"}:
            parser.error("Demo mode must listen on localhost")
        uvicorn.run(create_app(settings), host=args.host, port=args.port)
    elif args.command == "inspect-source":
        from evonext.compat.mongo_source import LegacyMongoSource
        from evonext.evidence.service import EvidenceService
        from evonext.evidence.store import MemoryAssets, MemorySnapshots
        if not 1 <= args.limit <= 100:
            parser.error("limit must be between 1 and 100")
        settings = Settings(demo=True, legacy_env_file=str(args.env_file), _env_file=None)
        reader = LegacyMongoSource(settings)
        try:
            if args.task_id:
                service = EvidenceService(MemorySnapshots(), MemoryAssets(), settings)
                snapshot = reader.capture(args.task_id, args.version, service)
                result = {"snapshot": snapshot.summary(), "persisted": False,
                          "profile": reader.profile, "meaning": "read-only inspection; memory discarded on exit"}
            else:
                result = {"items": reader.list(limit=args.limit), "profile": reader.profile}
            print(json.dumps(result, ensure_ascii=False, indent=2))
        finally:
            reader.close()
    elif args.command == "validate-bundle":
        from evonext.evidence.packages import import_bundle
        from evonext.evidence.store import MemoryAssets
        settings = Settings(demo=True, _env_file=None)
        if args.path.stat().st_size > settings.max_upload_bytes:
            parser.error("Bundle exceeds size limit")
        snapshot = import_bundle(args.path.read_bytes(), MemoryAssets(), settings)
        print(json.dumps(snapshot.summary(), ensure_ascii=False, indent=2))
    elif args.command == "replay-evaluation":
        from evonext.contracts.trajectory import Snapshot, load_json
        from evonext.evaluation.core import evaluate
        from evonext.evaluation.service import EvalRequest
        from evonext.evaluation.replay import ReplayGateway
        from evonext.evidence.packages import import_bundle
        from evonext.evidence.service import EvidenceService
        from evonext.evidence.store import MemoryAssets, MemorySnapshots
        settings = Settings(demo=True, _env_file=None)
        if args.path.stat().st_size > settings.max_upload_bytes or args.responses.stat().st_size > 1024 * 1024:
            parser.error("Replay input exceeds size limit")
        assets = MemoryAssets()
        raw = args.path.read_bytes()
        snapshot = (import_bundle(raw, assets, settings) if args.path.suffix.lower() == ".zip"
                    else Snapshot.create(raw, max_steps=settings.max_steps))
        service = EvidenceService(MemorySnapshots(), assets, settings)
        service.accept(snapshot)
        responses = load_json(args.responses.read_bytes())["responses"]
        request = EvalRequest(operation_id="synthetic-replay", investigation=args.investigation,
                              review_localization=args.review_localization, bind_decisions=args.bind_decisions)
        prompt = Path(__file__).parents[1].joinpath("evaluation/outcome.md").read_text(encoding="utf-8")
        result = evaluate(snapshot, request, service, ReplayGateway(responses), prompt, "synthetic-replay")
        result["native_result"]["synthetic_replay"] = True
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == "evaluate":
        from evonext.config import secret
        from evonext.evaluation.service import EvalRequest, submit, run
        from evonext.evidence.service import EvidenceService
        from evonext.evidence.store import stores
        from evonext.operations.ledger import Ledger
        from evonext.providers.gateway import ModelGateway
        settings = Settings()
        if settings.demo or not settings.postgres_dsn or not settings.model_calls_enabled:
            parser.error("Evaluation requires configured stores and explicitly enabled model calls")
        repository, assets = stores(settings)
        ledger = Ledger(secret(settings.postgres_dsn))
        gateway = None
        try:
            service = EvidenceService(repository, assets, settings)
            snapshot = service.get(args.snapshot_id)
            if snapshot is None:
                parser.error("Snapshot not found")
            submit(snapshot, EvalRequest(operation_id=args.operation_id, investigation=args.investigation,
                                         review_localization=args.review_localization,
                                         bind_decisions=args.bind_decisions), ledger)
            gateway = ModelGateway(settings)
            print(json.dumps(run(args.operation_id, service, ledger, gateway), ensure_ascii=False, indent=2))
        finally:
            if gateway is not None:
                gateway.close()
            ledger.close()
            repository.close()
            assets.close()
    elif args.command == "prepare-evaluation":
        from evonext.contracts.trajectory import Snapshot
        from evonext.evaluation.inputs import InputOptions, prepare_input
        from evonext.evidence.packages import import_bundle
        from evonext.evidence.store import MemoryAssets
        settings = Settings(demo=True, _env_file=None)
        if args.path.stat().st_size > settings.max_upload_bytes:
            parser.error("Input exceeds size limit")
        raw = args.path.read_bytes()
        snapshot = (import_bundle(raw, MemoryAssets(), settings) if args.path.suffix.lower() == ".zip"
                    else Snapshot.create(raw, max_steps=settings.max_steps))
        options = InputOptions(images=args.images, include_think=args.include_think,
                               max_images=args.max_images)
        print(json.dumps(prepare_input(snapshot, options), ensure_ascii=False, indent=2))
    elif args.command == "enqueue-integrity":
        from evonext.app.worker import verify
        receipt = verify.apply_async(args=[args.snapshot_id], queue="evonext.bulk")
        print(json.dumps({"delivery_id": receipt.id, "operation_id": "integrity-v1-" + args.snapshot_id,
                          "meaning": "broker submission, not completed validation"}))
    elif args.command == "model-probe":
        from evonext.providers.gateway import ModelGateway
        gateway = ModelGateway(Settings())
        try:
            print(json.dumps(gateway.complete([{"role": "user", "content": args.text}],
                                               max_tokens=64, operation_id=args.operation_id), ensure_ascii=False, indent=2))
        finally:
            gateway.close()

    elif args.command == "workshop":
        from evonext.skills.workshop import Workshop
        library = Workshop(args.root, args.owner)
        if args.action == "save":
            if args.file is None or not args.source:
                parser.error("save requires --file and one or more --source snapshot hashes")
            result = library.save(args.skill_id, args.file.read_text(encoding="utf-8"),
                expected_revision=args.expected, source_snapshots=args.source,
                reason=args.reason, actor=args.owner)
        elif args.action == "restore":
            if not args.revision or not args.expected:
                parser.error("restore requires --revision and --expected current revision")
            result = library.restore(args.skill_id, args.revision,
                expected_revision=args.expected, actor=args.owner)
        elif args.action == "archive":
            result = library.archive(args.skill_id, expected_revision=args.expected, actor=args.owner)
        elif args.action == "history":
            result = library.history(args.skill_id)
        elif args.action == "show":
            record, document = library.read(args.skill_id, args.revision)
            result = {"record": record, "document": document}
        elif args.action == "diff":
            if not args.expected or not args.revision:
                parser.error("diff requires --expected before and --revision after")
            result = {"diff": library.diff(args.skill_id, args.expected, args.revision)}
        else:
            if not args.revision:
                parser.error("export requires an exact --revision")
            result = library.export(args.skill_id, args.revision).model_dump(mode="json")
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == "list-available":
        from evonext.runtime.resources import Inventory, ResourceRequirements, get_resource_pool
        try:
            inventory = Inventory.model_validate_json(args.inventory.read_bytes())
            pool = get_resource_pool(inventory.kind, lambda: inventory)
            requirements = ResourceRequirements(driver=args.driver, resource_id=args.resource_id,
                                                capabilities=frozenset(args.capability))
            print(pool.list_available(requirements).model_dump_json(indent=2))
        except (ValueError, OSError) as exc:
            parser.error(str(exc))
    elif args.command == "prepare-trial":
        from evonext.contracts.runtime import RuntimeRequest
        from evonext.runtime.context import prepare_trial
        from evonext.evidence.packages import import_bundle
        from evonext.evidence.store import MemoryAssets
        from evonext.contracts.trajectory import load_json
        if args.request.stat().st_size > 1024 * 1024 or args.bundle.stat().st_size > 64 * 1024 * 1024:
            parser.error("Input exceeds local preparation limit")
        request = RuntimeRequest.model_validate_json(args.request.read_bytes())
        snapshot = import_bundle(args.bundle.read_bytes(), MemoryAssets(), Settings(demo=True, _env_file=None))
        plan = prepare_trial(request, snapshot)
        print(json.dumps({"plan_id": plan.id, "plan": load_json(plan.plan_json),
                          "context": load_json(plan.context_json)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
