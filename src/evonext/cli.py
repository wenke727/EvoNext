import argparse
import json
from pathlib import Path

from .config import Settings


def main():
    parser = argparse.ArgumentParser(prog="evonext")
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve")
    serve.add_argument("--demo", action="store_true")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    validate = commands.add_parser("validate-bundle")
    validate.add_argument("path", type=Path)
    enqueue = commands.add_parser("enqueue-integrity")
    enqueue.add_argument("snapshot_id")
    probe = commands.add_parser("model-probe")
    probe.add_argument("--text", required=True)
    args = parser.parse_args()
    if args.command == "serve":
        import uvicorn
        from .api import create_app
        settings = Settings(demo=True) if args.demo else Settings()
        if settings.demo and args.host not in {"127.0.0.1", "::1", "localhost"}:
            parser.error("Demo mode must listen on localhost")
        uvicorn.run(create_app(settings), host=args.host, port=args.port)
    elif args.command == "validate-bundle":
        from .packages import import_bundle
        from .storage import MemoryAssets
        settings = Settings(demo=True, _env_file=None)
        if args.path.stat().st_size > settings.max_upload_bytes:
            parser.error("Bundle exceeds size limit")
        snapshot = import_bundle(args.path.read_bytes(), MemoryAssets(), settings)
        print(json.dumps(snapshot.summary(), ensure_ascii=False, indent=2))
    elif args.command == "enqueue-integrity":
        from .worker import verify
        receipt = verify.apply_async(args=[args.snapshot_id], queue="evonext.bulk")
        print(json.dumps({"delivery_id": receipt.id, "operation_id": "integrity-v1-" + args.snapshot_id,
                          "meaning": "broker submission, not completed validation"}))
    elif args.command == "model-probe":
        from .models import ModelGateway
        gateway = ModelGateway(Settings())
        try:
            print(json.dumps(gateway.complete([{"role": "user", "content": args.text}],
                                               max_tokens=64), ensure_ascii=False, indent=2))
        finally:
            gateway.close()


if __name__ == "__main__":
    main()
