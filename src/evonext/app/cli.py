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
    if args.command == "case":
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
