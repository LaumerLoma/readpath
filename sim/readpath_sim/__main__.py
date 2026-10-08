"""Run experiments E1–E5 and write their figures and results into 3-experiments/.

    cd sim && python3 -m readpath_sim [e1 e2 ...] [--seeds 6]
"""

from __future__ import annotations

import argparse
from pathlib import Path

from .experiments import EXPERIMENTS, FOLDERS


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("only", nargs="*", metavar="experiment", help="e1 … e5 (default: all)")
    parser.add_argument("--seeds", type=int, default=6, help="seeds per treatment (default: 6)")
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parents[2] / "3-experiments")
    args = parser.parse_args()
    if unknown := set(args.only) - set(EXPERIMENTS):
        parser.error(f"unknown experiment: {', '.join(sorted(unknown))}")
    for key in args.only or EXPERIMENTS:
        print(EXPERIMENTS[key](args.out / FOLDERS[key], args.seeds), flush=True)


if __name__ == "__main__":
    main()
