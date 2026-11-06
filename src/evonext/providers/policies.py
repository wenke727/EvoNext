"""Versioned policy inputs; sandboxed rendering, never executable plugins."""
from dataclasses import dataclass
from pathlib import Path
import re

from jinja2 import DictLoader, StrictUndefined, meta
from jinja2.sandbox import SandboxedEnvironment

from evonext.contracts.trajectory import ContractError, encode_json, load_json, sha256

_NAME = re.compile(r"[a-z][a-z0-9_-]{0,63}")


@dataclass(frozen=True)
class FrozenPolicy:
    name: str
    version: str
    prompt: str
    config_json: bytes

    @property
    def config(self):
        return load_json(self.config_json)


def freeze_policy(root: Path, name: str, variables: dict) -> FrozenPolicy:
    """Only reviewed, local Markdown + JSON policies; no secrets or database defaults."""
    if not _NAME.fullmatch(name):
        raise ContractError("Invalid policy name")
    root = Path(root).resolve(strict=True)
    config_path = root / f"{name}.json"
    if config_path.is_symlink() or config_path.stat().st_size > 16384:
        raise ContractError("Unsafe policy configuration")
    config = load_json(config_path.read_bytes())
    required = {"schema_version", "output_schema", "model_profile", "max_tokens"}
    if set(config) != required or config["schema_version"] != "evonext.policy.v1":
        raise ContractError("Unexpected policy configuration keys")
    if any(not isinstance(config[k], str) or not config[k] for k in required - {"max_tokens"}):
        raise ContractError("Policy identities must be non-empty strings")
    if type(config["max_tokens"]) is not int or not 1 <= config["max_tokens"] <= 4096:
        raise ContractError("Invalid policy token budget")
    env = SandboxedEnvironment(undefined=StrictUndefined, autoescape=False,
                               keep_trailing_newline=True)
    env.globals.clear()
    templates, visiting = {}, set()

    def collect(filename):
        if not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}\.md", filename):
            raise ContractError("Only local named Markdown includes are permitted")
        if filename in visiting:
            raise ContractError("Policy include cycle")
        if filename in templates:
            return
        if len(templates) >= 16:
            raise ContractError("Too many policy dependencies")
        path = root / filename
        if path.is_symlink() or path.stat().st_size > 65536:
            raise ContractError("Unsafe or oversized policy template")
        text = path.read_text(encoding="utf-8")
        visiting.add(filename)
        templates[filename] = text
        for dependency in meta.find_referenced_templates(env.parse(text)):
            if dependency is None:
                raise ContractError("Dynamic policy includes are forbidden")
            collect(dependency)
        visiting.remove(filename)

    try:
        collect(f"{name}.md")
        env.loader = DictLoader(templates)
        # Restrict context to JSON values: no Python objects/methods or secret wrappers.
        clean_variables = load_json(encode_json(variables))
        prompt = env.get_template(f"{name}.md").render(**clean_variables)
    except ContractError:
        raise
    except Exception as exc:
        raise ContractError("Policy cannot be rendered; check required inputs and includes") from exc
    if len(prompt.encode("utf-8")) > 256 * 1024:
        raise ContractError("Rendered policy exceeds input budget")
    version = sha256(encode_json({"templates": templates, "config": config}))
    return FrozenPolicy(name, version, prompt, encode_json(config))
