"""Command-line interface: run benchmarks without the window, for scripting and automation."""

from __future__ import annotations

import argparse
import sys
import threading
from pathlib import Path

from asbench import APP_NAME, __version__, benchmarks
from asbench.core import fmt, scoring
from asbench.core.context import RunContext
from asbench.core.model import ERROR, OK, RunRecord, record_to_dict

EXAMPLES = """
examples:
  python main.py                               open the app
  python main.py --cli                         run the full suite in the terminal
  python main.py --cli --quick --only cpu,memory
  python main.py --cli --sustained 5 --sustained-mode both
  python main.py --cli --json run.json --report run.html
  python main.py --history                     list saved runs
  python main.py --setup-power                 how to enable power readings
"""


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="main.py",
        description=f"{APP_NAME} {__version__}",
        epilog=EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--cli", action="store_true", help="run benchmarks in the terminal instead of opening the app")
    p.add_argument("--only", metavar="LIST", help=f"comma-separated benchmarks to run (default: {','.join(benchmarks.SUITE)})")
    p.add_argument("--quick", action="store_true", help="shorter runs (about a quarter of the time, less precise)")
    p.add_argument("--sustained", metavar="MINUTES", type=float, help="run the sustained/thermal test for this many minutes")
    p.add_argument("--sustained-mode", choices=["cpu", "gpu", "both"], default="cpu", help="what the sustained test loads (default: cpu)")
    p.add_argument("--storage-path", metavar="FOLDER", help="folder (drive) for the storage test (default: system temp folder)")
    p.add_argument("--no-power", action="store_true", help="don't take power readings")
    p.add_argument("--json", metavar="FILE", type=Path, help="also write the results to a JSON file")
    p.add_argument("--csv", metavar="FILE", type=Path, help="also write the results to a CSV file")
    p.add_argument("--report", metavar="FILE", type=Path, help="also write a shareable HTML report")
    p.add_argument("--no-save", action="store_true", help="don't add this run to the saved history")
    p.add_argument("--calibrate", action="store_true", help="make this machine's results the 1,000-point reference")
    p.add_argument("--reset-calibration", action="store_true", help="go back to the built-in reference values")
    p.add_argument("--history", action="store_true", help="list saved runs and exit")
    p.add_argument("--system", action="store_true", help="show system information and exit")
    p.add_argument("--setup-power", action="store_true", help="show how to enable power readings and exit")
    p.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    return p


def wants_cli(args: argparse.Namespace) -> bool:
    """Options that only make sense in the terminal imply --cli."""
    return any([
        args.cli, args.history, args.system, args.setup_power, args.reset_calibration, args.sustained, args.calibrate,
        args.only, args.json, args.csv, args.report,
    ])


def main(args: argparse.Namespace) -> int:
    if args.setup_power:
        from asbench.core.power import power_status, setup_instructions

        print(setup_instructions())
        status = power_status()
        print(f"\nCurrent status: {'working' if status.available else status.reason}")
        return 0
    if args.system:
        return _print_system()
    if args.history:
        return _print_history()
    if args.reset_calibration:
        scoring.reset_references()
        print("Back to the built-in reference values.")
        if not (args.cli or args.sustained or args.calibrate):
            return 0

    if args.sustained:
        keys = ["sustained"]
    elif args.only:
        keys = [k.strip() for k in args.only.split(",") if k.strip()]
        try:
            for k in keys:
                benchmarks.get(k)
        except KeyError as exc:
            print(exc.args[0], file=sys.stderr)
            return 2
    else:
        keys = list(benchmarks.SUITE)

    options = {"sustained_mode": args.sustained_mode, "sustained_minutes": args.sustained or 3}
    if args.storage_path:
        options["storage_path"] = args.storage_path
    record = _run(keys, quick=args.quick, power=not args.no_power, options=options)
    if record is None:
        return 130

    _print_record(record)
    if record.results and not args.no_save:
        from asbench.core.history import History

        History().add(record)
    _write_outputs(record, args)

    if args.calibrate:
        if args.quick:
            print("\nNote: calibrating from a quick run is less precise than a standard run.")
        values = scoring.save_references(record.results)
        print(f"\nSaved {len(values)} reference values. This machine now scores 1,000 in every test.")
    if not record.complete:
        return 130
    return 1 if any(r.status == ERROR for r in record.results) else 0


class _Progress:
    """One updating line on a terminal; plain lines when output is redirected."""

    def __init__(self):
        self.tty = sys.stdout.isatty()
        self.title = ""
        self.fraction = 0.0
        self.text = ""
        self._last = ""
        self._lock = threading.Lock()

    def start(self, key: str):
        self.title = benchmarks.get(key).title
        self.fraction, self.text = 0.0, ""
        self.draw()

    def progress(self, fraction: float):
        self.fraction = fraction
        self.draw()

    def status(self, text: str):
        self.text = text
        if not self.tty:
            print(f"  {self.title}: {text}", flush=True)
        self.draw()

    def draw(self):
        if not self.tty:
            return
        with self._lock:
            filled = int(self.fraction * 24)
            line = f"\r  {self.title:<14} {'█' * filled}{'░' * (24 - filled)} {self.fraction * 100:3.0f}%  {self.text}"
            line = line[:110].ljust(len(self._last))
            sys.stdout.write(line)
            sys.stdout.flush()
            self._last = line

    def clear(self):
        if self.tty and self._last:
            sys.stdout.write("\r" + " " * len(self._last) + "\r")
            sys.stdout.flush()
            self._last = ""


def _run(keys, *, quick, power, options) -> RunRecord | None:
    from asbench.core.runner import run_many
    from asbench.core.sysinfo import collect

    info = collect()
    print(f"{APP_NAME} {__version__} · {info.chip or info.arch} · {info.core_summary} · {info.memory_gb:g} GB")
    if power:
        from asbench.core.power import power_status

        status = power_status()
        print("Power readings: on" if status.available else f"Power readings: off ({status.reason} Run --setup-power.)")
    print()

    bar = _Progress()
    per_benchmark = {"key": None}

    def on_event(name, payload):
        if name == "benchmark_started":
            per_benchmark["key"] = payload
            bar.start(payload)
        elif name == "benchmark_finished":
            bar.clear()
            _print_result_line(payload)
        elif name == "sustained_point":
            bar.clear()
            parts = [f"{fmt.duration(payload['t']):>10}"]
            if payload.get("cpu") is not None:
                parts.append(f"CPU {payload['cpu']:,.1f} ops/s")
            if payload.get("gpu") is not None:
                parts.append(f"GPU {payload['gpu']:,.0f} GFLOPS")
            if payload.get("power") is not None:
                parts.append(f"{payload['power']:.1f} W")
            if payload.get("thermal"):
                parts.append(payload["thermal"])
            print("  " + " · ".join(parts))

    ctx = RunContext(quick=quick, on_progress=bar.progress, on_status=bar.status, on_event=on_event, options=options)
    holder: list[RunRecord] = []
    worker = threading.Thread(target=lambda: holder.append(run_many(keys, ctx, power=power)), daemon=True)
    worker.start()
    try:
        while worker.is_alive():
            worker.join(0.2)
    except KeyboardInterrupt:
        bar.clear()
        print("\nCancelling…", flush=True)
        ctx.cancel()
        worker.join()
    bar.clear()
    if not holder:
        return None
    if not holder[0].complete:
        print("Cancelled.")
    return holder[0]


def _print_result_line(r):
    tail = {OK: fmt.score(r.score)}.get(r.status, r.status.upper())
    print(f"  {r.title:<14} {tail:>8}   {fmt.duration(r.duration_s)}")


def _print_record(record: RunRecord) -> None:
    print()
    for r in record.results:
        head = f"{r.title}  ·  {fmt.score(r.score) if r.score else r.status}"
        if r.backend:
            head += f"  ·  {r.backend}"
        print(head)
        if r.error:
            print(f"  Error: {r.error}")
        group = None
        for m in r.metrics:
            if m.group != group:
                group = m.group
                if group:
                    gs = r.group_scores.get(group)
                    print(f"  {group}" + (f"  ({fmt.score(gs)})" if gs else ""))
            indent = "    " if m.group else "  "
            print(f"{indent}{m.name:<34} {fmt.value(m.value, m.unit):>16}   {fmt.score(m.score) if m.score else '':>7}")
        if r.power and r.power.available:
            print(f"  Power: {fmt.value(r.power.avg_w, 'W')} average, {fmt.value(r.power.peak_w, 'W')} peak"
                  + (f", {r.efficiency:,.0f} points per watt" if r.efficiency else ""))
        for note in r.notes:
            print(f"  · {note}")
        print()
    if record.composite is not None:
        print(f"Overall score: {fmt.score(record.composite)}  (1,000 = {'your calibrated baseline' if record.reference == 'custom' else 'built-in reference'})")


def _write_outputs(record: RunRecord, args) -> None:
    import json

    from asbench.core import history, report

    if args.json:
        args.json.write_text(json.dumps(record_to_dict(record), indent=2), encoding="utf-8")
        print(f"Wrote {args.json}")
    if args.csv:
        history.export_csv([record], args.csv)
        print(f"Wrote {args.csv}")
    if args.report:
        args.report.write_text(report.render(record), encoding="utf-8")
        print(f"Wrote {args.report}")


def _print_system() -> int:
    from asbench.core.sysinfo import collect

    for key, value in collect().as_dict().items():
        print(f"{key.replace('_', ' '):<18} {value}")
    return 0


def _print_history() -> int:
    from asbench.core.history import History

    records = History().load()
    if not records:
        print("No saved runs yet.")
        return 0
    keys = benchmarks.SUITE
    titles = [benchmarks.get(k).short_title for k in keys]
    print(f"{'When':<22} {'Type':<10} {'Mode':<9} {'Overall':>8} " + " ".join(f"{t:>8}" for t in titles))
    for r in records:
        cells = []
        for k in keys:
            res = r.result(k)
            cells.append(fmt.score(res.score) if res and res.score else "")
        kind = r.kind if r.complete else f"{r.kind}*"
        print(f"{fmt.when(r.timestamp):<22} {kind:<10} {r.mode:<9} {fmt.score(r.composite) if r.composite else '':>8} "
              + " ".join(f"{c:>8}" for c in cells))
    if any(not r.complete for r in records):
        print("\n* cancelled part-way")
    return 0
