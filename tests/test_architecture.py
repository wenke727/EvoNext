"""Executable, intentionally small ownership rules; not a universal static analyzer."""
import ast
from pathlib import Path
import re
import runpy

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src/evonext"


def imports(path):
    result = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            result.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.append(node.module)
    return result


def test_layers_do_not_depend_on_hosts_or_old_implementation():
    errors = []
    for path in SRC.rglob("*.py"):
        names = imports(path)
        relative = path.relative_to(SRC)
        for name in names:
            if name.startswith(("flywheel", "offline.skill_workshop", "agent_runtime")):
                errors.append((str(relative), name))
            if relative.parts[0] != "app" and name.startswith("evonext.app"):
                errors.append((str(relative), name))
            if relative.parts[0] == "contracts" and name.startswith((
                    "fastapi", "httpx", "sqlalchemy", "pymongo", "minio", "celery",
                    "evonext.evidence", "evonext.providers", "evonext.skills", "evonext.runtime")):
                errors.append((str(relative), name))
            if relative.parts[0] == "runtime" and name.startswith("evonext.skills"):
                errors.append((str(relative), name))
            if relative.parts[0] == "skills" and name.startswith(("evonext.runtime", "evonext.providers", "httpx")):
                errors.append((str(relative), name))
    assert not errors


def test_old_flat_paths_not_kept_as_second_implementation():
    for name in ("api", "cli", "worker", "domain", "models", "storage", "packages", "legacy", "ledger", "telemetry", "verification"):
        assert not (SRC / f"{name}.py").exists(), name


def test_http_host_does_not_import_model_gateway_or_runtime_execution():
    names = imports(SRC / "app/api.py")
    assert not any(name.startswith(("evonext.providers.gateway", "evonext.app.worker", "evonext.runtime")) for name in names)
    tree = ast.parse((SRC / "app/api.py").read_text())
    for function in ast.walk(tree):
        if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        is_get = any(isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr == "get"
                     for d in function.decorator_list)
        if is_get:
            calls = [n.func.attr for n in ast.walk(function) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)]
            assert not set(calls) & {"complete", "apply_async", "publish", "put", "accept", "save"}, function.name


def test_full_rebuild_package_present_and_no_default_mongo_retirement():
    required = ["README.md", "00_REVIEW_AND_GAPS.md", "01_PRODUCT_PRD.md", "02_DOMAIN_CONTRACTS.md",
        "03_ARCHITECTURE.md", "04_API_AND_WORKBENCH.md", "05_CLEANROOM_MIGRATION.md", "06_ACCEPTANCE.md",
        "07_IMPLEMENTATION_PROMPT.md", "08_SKILLS_RUNTIME_AND_PIPELINE.md", "SOURCE_MANIFEST.json"]
    for name in required:
        assert (ROOT / "docs/rebuild" / name).is_file(), name
    content = (ROOT / "docs/rebuild/06_ACCEPTANCE.md").read_text()
    assert set(re.findall(r"AC-(\d{3})", content)) == {f"{i:03d}" for i in range(1, 64)}
    assert "推荐优先验证" not in (ROOT / "docs/rebuild/03_ARCHITECTURE.md").read_text()
    assert "Mongo + MinIO + PostgreSQL 保留" in (ROOT / "docs/rebuild/README.md").read_text()


def test_retained_synthetic_spec_fixtures():
    runpy.run_path(str(ROOT / "docs/rebuild/examples/validate_examples.py"))


def test_python_entrypoints_use_current_package_paths():
    assert 'evonext.app.cli:main' in (ROOT / "pyproject.toml").read_text()
    assert 'evonext.app.api:create_app' in (ROOT / "Dockerfile").read_text()
    assert 'evonext.app.worker:app' in (ROOT / "compose.yaml").read_text()
