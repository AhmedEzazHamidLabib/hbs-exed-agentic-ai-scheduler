import os
import json
import sys
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()


def print_banner(text: str):
    print("\n" + "=" * 60)
    print(f"  {text}")
    print("=" * 60 + "\n")


def run_pipeline(poll_interval: int = 300, max_hours: int = 48):
    """
    Full pipeline:
    1. Constraint extraction (parser.py)
    2. Schedule generation (scheduler.py)
    3. Outreach (outreach.py)
    4. Coordinator polling loop (coordinator.py)
    """

    # -----------------------------------------------------------------------
    # Stage 1 — Constraint Extraction
    # -----------------------------------------------------------------------
    print_banner("Stage 1 — Constraint Extraction")

    from parser import run_parser_langchain
    constraints = run_parser_langchain()

    if not constraints:
        print("[main] No constraints extracted — exiting.")
        sys.exit(1)

    if not constraints.get("ready"):
        print("[main] Constraints not marked ready — exiting.")
        sys.exit(1)

    print(f"[main] Constraints ready. Saved to constraints.json")

    # -----------------------------------------------------------------------
    # Stage 2 — Schedule Generation
    # -----------------------------------------------------------------------
    print_banner("Stage 2 — Schedule Generation")

    from scheduler import run_scheduler_langchain
    schedule = run_scheduler_langchain("constraints.json")

    if not schedule:
        print("[main] Schedule generation failed — exiting.")
        sys.exit(1)

    print(f"[main] Schedule generated. Request ID: {schedule.get('request_id')}")
    print(f"       {len(schedule.get('options', []))} option(s), "
          f"{len(schedule.get('hierarchy', []))} party(s) in hierarchy")

    # -----------------------------------------------------------------------
    # Stage 3 — Outreach
    # -----------------------------------------------------------------------
    print_banner("Stage 3 — Outreach")

    from outreach import run_outreach
    sent = run_outreach()

    if not sent:
        print("[main] No emails sent — exiting.")
        sys.exit(1)

    sent_count = sum(1 for e in sent if e.get("sent"))
    print(f"[main] {sent_count}/{len(sent)} email(s) sent successfully.")

    # -----------------------------------------------------------------------
    # Stage 4 — Coordinator Polling Loop
    # -----------------------------------------------------------------------
    print_banner("Stage 4 — Coordinator Loop")
    print(f"  Polling every {poll_interval // 60} min for up to {max_hours} hours.")
    print("  Press Ctrl+C to stop manually.\n")

    from coordinator import run_polling_loop
    try:
        run_polling_loop(
            request_id=schedule.get("request_id"),
            interval_seconds=poll_interval,
            max_hours=max_hours,
        )
    except KeyboardInterrupt:
        print("\n[main] Polling stopped by user.")

    # -----------------------------------------------------------------------
    # Done
    # -----------------------------------------------------------------------
    print_banner("Pipeline Complete")
    from state import get_request
    state = get_request(schedule.get("request_id"))
    if state:
        print(f"  Final status:  {state['status']}")
        print(f"  Request ID:    {state['request_id']}")
        print(f"  Last updated:  {state['updated_at']}")
        print()


if __name__ == "__main__":
    # Optional args: python main.py [poll_interval_seconds] [max_hours]
    interval = int(sys.argv[1]) if len(sys.argv) > 1 else 120
    hours = int(sys.argv[2]) if len(sys.argv) > 2 else 48

    run_pipeline(poll_interval=interval, max_hours=hours)