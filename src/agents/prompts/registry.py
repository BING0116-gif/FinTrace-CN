"""Fail-closed, hash-addressable prompt templates."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any

DEFAULT_TEMPLATES_DIR = Path(__file__).with_name("templates")
_REGISTRY: dict[tuple[str, int], "PromptSpec"] = {}
_USAGE: list[dict[str, Any]] = []

@dataclass(frozen=True)
class PromptSpec:
    prompt_name: str
    prompt_version: int
    template: str
    variables: list[str]
    prompt_hash: str
    model: str | None = None
    temperature: float | None = None
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]: return asdict(self)

def _frontmatter(text: str, path: Path) -> tuple[dict[str, Any], str]:
    if not text.startswith("---"):
        raise ValueError(f"Prompt template requires frontmatter: {path.name}")
    parts = text.split("---", 2)
    if len(parts) != 3: raise ValueError(f"Malformed prompt frontmatter: {path.name}")
    values: dict[str, Any] = {}
    for line in parts[1].splitlines():
        if not line.strip() or ":" not in line: continue
        key, value = line.split(":", 1); value = value.strip(); key = key.strip()
        if value.startswith("["):
            try: value = json.loads(value)
            except json.JSONDecodeError: value = [item.strip() for item in value[1:-1].split(",") if item.strip()]
        elif value.lower() in {"null", "none"}: value = None
        elif value.isdigit(): value = int(value)
        elif re.fullmatch(r"-?\d+\.\d+", value): value = float(value)
        elif len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}: value = value[1:-1]
        values[key] = value
    return values, parts[2].lstrip("\r\n")

def load_registry(templates_dir: str | Path = DEFAULT_TEMPLATES_DIR) -> dict[str, PromptSpec]:
    directory = Path(templates_dir)
    if not directory.is_dir(): raise FileNotFoundError(f"Prompt registry directory not found: {directory}")
    loaded: dict[tuple[str, int], PromptSpec] = {}
    for path in sorted(directory.glob("*.md")):
        metadata, template = _frontmatter(path.read_text(encoding="utf-8"), path)
        name = str(metadata.get("name") or metadata.get("prompt_name") or "").strip()
        if not name: raise ValueError(f"Prompt name missing: {path.name}")
        version = int(metadata.get("version", metadata.get("prompt_version", 0)))
        if version <= 0: raise ValueError(f"Prompt version must be positive: {path.name}")
        variables = metadata.get("variables", [])
        if isinstance(variables, str): variables = [item.strip() for item in variables.split(",") if item.strip()]
        variables = [str(item) for item in variables]
        digest = hashlib.sha256(template.encode("utf-8")).hexdigest()
        spec = PromptSpec(name, version, template, variables, digest, metadata.get("model"), metadata.get("temperature"), str(metadata.get("created_at") or ""))
        key = (name, version)
        if key in loaded and loaded[key].prompt_hash != digest: raise ValueError(f"Prompt version is immutable but content differs: {name} v{version}")
        loaded[key] = spec
    if not loaded: raise ValueError(f"Prompt registry is empty: {directory}")
    _REGISTRY.clear(); _REGISTRY.update(loaded)
    return {name: max((spec for (candidate, _), spec in loaded.items() if candidate == name), key=lambda item: item.prompt_version) for name in {key[0] for key in loaded}}

def _ensure_loaded() -> None:
    if not _REGISTRY: load_registry()

def _resolve(name: str) -> PromptSpec:
    _ensure_loaded()
    if "@" in name:
        base, raw = name.rsplit("@", 1); key = (base, int(raw))
        if key not in _REGISTRY: raise KeyError(f"Unknown prompt: {name}")
        return _REGISTRY[key]
    options = [spec for (candidate, _), spec in _REGISTRY.items() if candidate == name]
    # A caller may load an isolated registry for validation tests; restore the
    # application registry on demand rather than leaking that process-local
    # override into the agent.
    if not options and Path(DEFAULT_TEMPLATES_DIR).is_dir():
        load_registry(DEFAULT_TEMPLATES_DIR)
        options = [spec for (candidate, _), spec in _REGISTRY.items() if candidate == name]
    if not options: raise KeyError(f"Unknown prompt: {name}")
    return max(options, key=lambda item: item.prompt_version)

def render(prompt_name: str, **variables: Any) -> str:
    spec = _resolve(prompt_name)
    expected = set(spec.variables); actual = set(variables)
    missing, extra = sorted(expected - actual), sorted(actual - expected)
    if missing or extra: raise ValueError(f"Prompt variables mismatch for {prompt_name}: missing={missing}, extra={extra}")
    return spec.template.format(**variables)

def prompt_hash(prompt_name: str) -> str: return _resolve(prompt_name).prompt_hash

def record_usage(prompt_name: str, model: str | None, temperature: float | None) -> dict[str, Any]:
    spec = _resolve(prompt_name)
    usage = {"prompt_name": spec.prompt_name, "prompt_version": spec.prompt_version, "prompt_hash": spec.prompt_hash, "model": model, "temperature": temperature, "recorded_at": datetime.now(timezone.utc).isoformat()}
    _USAGE.append(usage); return dict(usage)

def usage_records() -> list[dict[str, Any]]: return [dict(item) for item in _USAGE]
