"""CLI entry point: python -m autosentinel <log_path>"""

import argparse
import sys

from autosentinel import DiagnosticError, run_pipeline


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="autosentinel",
        description="AutoSentinel Core Diagnostic Engine",
    )
    parser.add_argument("log_path", help="Path to the JSON error log file")
    args = parser.parse_args()

    print("[AutoSentinel] Running diagnostic pipeline...")
    try:
        report_path = run_pipeline(args.log_path)
        print(f"[AutoSentinel] Report written to {report_path}")
        sys.exit(0)
    except FileNotFoundError as exc:
        print(f"[AutoSentinel] Error: {exc}", file=sys.stderr)
        sys.exit(1)
    except DiagnosticError as exc:
        print(f"[AutoSentinel] Pipeline error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":  # pragma: no cover
    main()
