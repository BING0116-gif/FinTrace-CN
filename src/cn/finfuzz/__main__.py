"""Small CLI for inventorying deterministic FinFuzz mutations."""
from __future__ import annotations
import argparse, json
from .suite import MutationOperators, generate_mutation_specs

def main(argv=None):
    parser = argparse.ArgumentParser(); parser.add_argument("--operator", default=",".join(item.value for item in MutationOperators)); parser.add_argument("--out", default="output/benchmark/finfuzz")
    args = parser.parse_args(argv); operators = [MutationOperators(item.strip()) for item in args.operator.split(",") if item.strip()]
    payload = {"schema_version": "cn-finfuzz-1.0.0", "operators": [item.value for item in operators], "status": "mutation inventory only; no detection metrics measured"}
    from pathlib import Path
    path = Path(args.out); path.mkdir(parents=True, exist_ok=True); (path / "inventory.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"); print(json.dumps(payload, ensure_ascii=False)); return 0

if __name__ == "__main__": raise SystemExit(main())
