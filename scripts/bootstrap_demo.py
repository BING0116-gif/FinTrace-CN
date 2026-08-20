"""Create license-safe, deterministic demo snapshots for local use."""

from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.cn.demo_data import ensure_demo_snapshots  # noqa: E402


def main() -> int:
    destination = ROOT / "data" / "snapshots" / "cn"
    written = ensure_demo_snapshots(destination)
    if written:
        print(f"Created {len(written)} illustrative snapshots in {destination}")
    else:
        print(f"Illustrative demo snapshots already exist in {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
