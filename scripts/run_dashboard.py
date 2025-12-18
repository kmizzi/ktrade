#!/usr/bin/env python3
"""
Dashboard runner script.
Launches the KTrade Streamlit dashboard.

Usage:
    python scripts/run_dashboard.py
    python scripts/run_dashboard.py --port 8502
"""

import subprocess
import sys
import argparse
from pathlib import Path


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Launch the KTrade dashboard"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8501,
        help="Port to run the dashboard on (default: 8501)"
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Don't open browser automatically"
    )
    return parser.parse_args()


def main():
    """Run the dashboard."""
    args = parse_args()

    # Get path to dashboard app
    project_root = Path(__file__).parent.parent
    app_path = project_root / "src" / "dashboard" / "app.py"

    if not app_path.exists():
        print(f"Error: Dashboard app not found at {app_path}")
        return 1

    print("=" * 50)
    print("       KTRADE DASHBOARD")
    print("=" * 50)
    print(f"\nStarting dashboard on port {args.port}...")
    print(f"Open http://localhost:{args.port} in your browser\n")

    # Build streamlit command
    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(app_path),
        "--server.port",
        str(args.port),
        "--server.headless",
        "true" if args.no_browser else "false",
        "--theme.base",
        "dark",
    ]

    try:
        # Run streamlit
        subprocess.run(cmd, cwd=str(project_root))
    except KeyboardInterrupt:
        print("\nDashboard stopped.")
        return 0
    except Exception as e:
        print(f"Error running dashboard: {e}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
