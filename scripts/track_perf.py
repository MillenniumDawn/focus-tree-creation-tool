"""Time each hot area on deterministic synthetic workloads.

Writes a JSON report (area, workload size, median ms, call counts where
meaningful) to stdout, and to a file with ``--out``. Heavy timing lives here,
not in the pytest suite: ``tests/test_perf_tracking.py`` only smoke-tests the
harness itself on a tiny preset.

Usage:
    python scripts/track_perf.py [--preset full|quick] [--areas parse,build]
        [--repeats N] [--out report.json] [--list-areas]
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from hoi4cm.perf import (  # noqa: E402  # pylint: disable=wrong-import-position
    AREAS,
    run_all,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--preset",
        choices=("full", "quick", "tiny"),
        default="full",
        help="workload sizes (default: full)",
    )
    parser.add_argument(
        "--areas",
        default=",".join(AREAS),
        help="comma-separated subset of areas (default: all)",
    )
    parser.add_argument(
        "--repeats",
        type=int,
        default=None,
        help="override the preset's repeat count",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="also write the JSON report to this path",
    )
    parser.add_argument(
        "--list-areas",
        action="store_true",
        help="print the tracked area names and exit",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.list_areas:
        print("\n".join(AREAS))
        return 0
    wanted = [name.strip() for name in args.areas.split(",") if name.strip()]
    unknown = [name for name in wanted if name not in AREAS]
    if unknown:
        print(f"unknown areas: {', '.join(unknown)}", file=sys.stderr)
        return 2
    report = run_all(areas=wanted, preset=args.preset, repeats=args.repeats)
    text = report.to_json()
    print(text)
    if args.out:
        parent = os.path.dirname(os.path.abspath(args.out))
        os.makedirs(parent, exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(text + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
