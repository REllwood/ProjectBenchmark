"""Apple System Benchmark.

    python main.py            open the app
    python main.py --cli      run the benchmarks in the terminal
    python main.py --help     all options

Keep the imports at the top of this file to the standard library. The CPU benchmark's
worker processes re-run this module's top level when they start, so anything heavy here
would slow down every worker.
"""

import logging
import sys


def main() -> int:
    import multiprocessing

    multiprocessing.freeze_support()
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

    from asbench.cli import build_parser, main as cli_main, wants_cli

    args = build_parser().parse_args()
    if wants_cli(args):
        return cli_main(args)

    from asbench.ui.app import run_gui

    return run_gui(args)


if __name__ == "__main__":
    sys.exit(main())
