"""Create a safe copy of a run with one CARD-12 demo failure injected."""
from __future__ import annotations
import argparse
from pathlib import Path
from src.cn.evidence_pack import inject_failure_scenario, list_failure_injections

def main(argv=None):
    parser = argparse.ArgumentParser(); parser.add_argument("run_dir"); parser.add_argument("scenario", choices=[item["id"] for item in list_failure_injections()]); parser.add_argument("--out", required=True)
    args = parser.parse_args(argv); result = inject_failure_scenario(Path(args.run_dir), args.scenario, Path(args.out)); print(result); return 0

if __name__ == "__main__": raise SystemExit(main())
