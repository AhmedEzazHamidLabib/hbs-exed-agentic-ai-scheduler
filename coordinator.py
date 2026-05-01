import os
import json
from datetime import datetime
from typing import Optional

from dotenv import load_dotenv

from state import (
    Status, get_request, get_latest, transition,
    create_request, advance_party, set_counter_proposal,
    resolve_counter_proposal, reset_colocation_group
)

load_dotenv()

REPLIES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "replies.json")
SCHEDULE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schedule_options.json")
CONSTRAINTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "constraints.json")
EMAILS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "emails_options.json")


# ---------------------------------------------------------------------------
# File helpers
# ---------------------------------------------------------------------------

def load_replies() -> list:
    if os.path.exists(REPLIES_FILE):
        with open(REPLIES_FILE, "r") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return []
    return []


def load_emails_file() -> list:
    if os.path.exists(EMAILS_FILE):
        with open(EMAILS_FILE, "r") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return []
    return []


def load_schedule() -> dict:
    if os.path.exists(SCHEDULE_FILE):
        with open(SCHEDULE_FILE, "r") as f:
            data = json.load(f)
            return data[-1] if isinstance(data, list) else data
    return {}


def save_schedule(schedule: dict):
    if os.path.exists(SCHEDULE_FILE):
        with open(SCHEDULE_FILE, "r") as f:
            try:
                records = json.load(f)
                if not isinstance(records, list):
                    records = [records]
            except json.JSONDecodeError:
                records = []
    else:
        records = []

    if records:
        records[-1] = schedule
    else:
        records.append(schedule)

    with open(SCHEDULE_FILE, "w") as f:
        json.dump(records, f, indent=2)


def save_constraints(constraints: dict):
    with open(CONSTRAINTS_FILE, "w") as f:
        json.dump(constraints, f, indent=2)


def load_processed_replies() -> set:
    processed_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "processed_replies.json")
    if os.path.exists(processed_file):
        with open(processed_file, "r") as f:
            try:
                return set(json.load(f))
            except json.JSONDecodeError:
                return set()
    return set()


def save_processed_replies(processed: set):
    processed_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "processed_replies.json")
    with open(processed_file, "w") as f:
        json.dump(list(processed), f, indent=2)


# ---------------------------------------------------------------------------
# Coordinator actions
# ---------------------------------------------------------------------------

def mark_party_confirmed(schedule: dict, party_name: str, confirmed_option: Optional[str]) -> dict:
    for party in schedule["hierarchy"]:
        if party["party"] == party_name:
            party["status"] = "CONFIRMED"
            if confirmed_option:
                party["confirmed_option"] = confirmed_option
            print(f"  [coordinator] ✓ {party_name} confirmed" + (f" option {confirmed_option}" if confirmed_option else ""))
    return schedule


def get_next_waiting_party(schedule: dict) -> Optional[dict]:
    for party in schedule["hierarchy"]:
        if party["status"] == "WAITING":
            return party
    return None


def all_confirmed(schedule: dict) -> bool:
    return all(p["status"] == "CONFIRMED" for p in schedule["hierarchy"])


def get_colocation_group_members(schedule: dict, group_label: str) -> list:
    return [
        p for p in schedule["hierarchy"]
        if p.get("colocation_group") == group_label
    ]


def reset_colocation_members(schedule: dict, group_label: str, excluding_party: str) -> tuple:
    reset = []
    for party in schedule["hierarchy"]:
        if (
            party.get("colocation_group") == group_label
            and party["party"] != excluding_party
            and party["status"] == "CONFIRMED"
        ):
            party["status"] = "PENDING"
            reset.append(party["party"])
            print(f"  [coordinator] ↺ {party['party']} reset to PENDING (co-location group {group_label} affected)")
    return schedule, reset


def promote_next_waiting(schedule: dict) -> Optional[dict]:
    for party in schedule["hierarchy"]:
        if party["status"] == "WAITING":
            party["status"] = "PENDING"
            print(f"  [coordinator] → {party['party']} promoted to PENDING")
            return party
    return None


def print_escalation_brief(party_name: str, request_id: str, schedule: dict):
    party = next((p for p in schedule["hierarchy"] if p["party"] == party_name), {})
    print("\n" + "=" * 60)
    print("  ⚠  ESCALATION BRIEF")
    print("=" * 60)
    print(f"  Request:    {request_id}")
    print(f"  Party:      {party_name}")
    print(f"  Contact:    {party.get('contact_name')} ({party.get('contact_email')})")
    print(f"  Via:        {party.get('contact_via')}")
    print(f"  Sessions:   {', '.join(party.get('sessions', []))}")
    print(f"  Summary:    {schedule.get('summary', '')}")
    print("  Recommended action: Call directly to confirm availability.")
    print("=" * 60 + "\n")


def print_counter_proposal_brief(reply: dict, schedule: dict):
    print("\n" + "=" * 60)
    print("  ↔  COUNTER-PROPOSAL RECEIVED")
    print("=" * 60)
    print(f"  From:       {reply['party']} ({reply['contact_email']})")
    print(f"  Summary:    {reply['summary']}")
    if reply.get("new_constraints"):
        nc = reply["new_constraints"]
        print(f"  New clauses: {nc.get('override_clauses', [])}")
        print(f"  New when:    {nc.get('override_when', [])}")
        print(f"  Notes:       {nc.get('notes', '')}")
    if reply.get("colocation_group"):
        group = reply["colocation_group"]
        members = get_colocation_group_members(schedule, group)
        confirmed_members = [m["party"] for m in members if m["status"] == "CONFIRMED"]
        if confirmed_members:
            print(f"\n  ⚠  Co-location impact: {', '.join(confirmed_members)} already confirmed")
            print(f"     If accepted, they will be reset to PENDING and re-contacted.")
    print("=" * 60)
    print("\n  Options:")
    print("  [A] Accept counter-proposal → regenerate schedule + restart outreach")
    print("  [R] Reject counter-proposal → re-send original options to this party")
    print("  [E] Escalate → flag for manual coordinator intervention\n")


# ---------------------------------------------------------------------------
# Main coordination loop
# ---------------------------------------------------------------------------
def run_coordinator(request_id: str = None) -> dict:
    """
    Process all unhandled replies and drive state transitions.
    Only processes replies received after the most recent outreach send time
    for each party — prevents stale replies from previous rounds bleeding through.
    """
    schedule = load_schedule()
    if not schedule:
        print("[coordinator] No schedule found. Run scheduler.py first.")
        return {}

    rid = request_id or schedule.get("request_id")
    if not rid:
        print("[coordinator] No request ID found.")
        return {}

    state = get_request(rid)
    if not state:
        state = create_request(rid, schedule.get("summary", ""))

    print(f"\n[coordinator] Processing request {rid} (status: {state['status']})")

    all_replies = load_replies()
    processed = load_processed_replies()

    # Build lookup: party → most recent sent_at for this request
    all_emails = load_emails_file()
    latest_sent_per_party = {}
    for e in all_emails:
        if e.get("request_id") == rid and e.get("sent"):
            party = e.get("party", "")
            sent_at = e.get("sent_at", "")
            if party not in latest_sent_per_party or sent_at > latest_sent_per_party[party]:
                latest_sent_per_party[party] = sent_at

    # Filter: only unprocessed replies received AFTER the email was sent to that party
    new_replies = [
        r for r in all_replies
        if r.get("request_id") == rid
        and r.get("reply_msg_id") not in processed
        and r.get("replied_at", "") > latest_sent_per_party.get(r.get("party", ""), "")
    ]

    if not new_replies:
        print("[coordinator] No new replies to process.")
        return {"status": state["status"], "schedule": schedule}

    print(f"[coordinator] Processing {len(new_replies)} new reply(s)...\n")

    for reply in new_replies:
        classification = reply["classification"]
        party_name = reply["party"]
        print(f"[coordinator] Reply from {party_name}: {classification} ({reply['confidence']} confidence)")
        print(f"  Summary: {reply['summary']}")

        # --- CONFIRMED ---
        if classification == "CONFIRMED":
            schedule = mark_party_confirmed(schedule, party_name, reply.get("confirmed_option"))
            save_schedule(schedule)

            if all_confirmed(schedule):
                transition(rid, Status.CONFIRMED, note="All parties confirmed — schedule locked")
                schedule["status"] = "CONFIRMED"
                save_schedule(schedule)
                print("\n" + "=" * 60)
                print("  ✓ ALL PARTIES CONFIRMED — SCHEDULE LOCKED")
                print("=" * 60)
                print(json.dumps(schedule, indent=2))
            else:
                next_party = promote_next_waiting(schedule)
                save_schedule(schedule)
                if next_party:
                    print(f"[coordinator] Triggering outreach for next party: {next_party['party']}")
                    from outreach import run_outreach
                    run_outreach()

        # --- COUNTER_PROPOSED ---
        elif classification == "COUNTER_PROPOSED":
            set_counter_proposal(rid, reply["summary"])
            print_counter_proposal_brief(reply, schedule)

            while True:
                decision = input("  Your decision [A/R/E]: ").strip().upper()
                if decision in ("A", "R", "E"):
                    break
                print("  Please enter A, R, or E.")

            if decision == "A":
                colocation_group = reply.get("colocation_group")

                # Always set recontact_reason — counter-proposer and colocation members all need re-contact
                recontact_reason = f"{party_name} proposed a schedule change. Updated options are being sent to all affected parties."

                # Reset co-location group members (excluding counter-proposer)
                if colocation_group:
                    schedule, reset_parties = reset_colocation_members(schedule, colocation_group, party_name)
                    save_schedule(schedule)

                # Reset the counter-proposing party themselves on the same schedule object
                for party in schedule["hierarchy"]:
                    if party["party"] == party_name:
                        party["status"] = "PENDING"
                        print(f"  [coordinator] ↺ {party_name} reset to PENDING (counter-proposer must re-confirm new schedule)")
                save_schedule(schedule)

                if reply.get("merged_constraints"):
                    merged = reply["merged_constraints"]
                    merged.pop("_merge_log", None)
                    merged["ready"] = True
                    merged["request_id"] = rid
                    save_constraints(merged)
                    print(f"[coordinator] Updated constraints saved.")

                resolve_counter_proposal(rid, accept=True)
                print("[coordinator] Regenerating schedule with updated constraints...")
                from scheduler import run_scheduler_langchain
                new_schedule = run_scheduler_langchain(CONSTRAINTS_FILE)

                if new_schedule:
                    print("[coordinator] Triggering outreach with updated schedule...")
                    from outreach import run_outreach
                    run_outreach(recontact_reason=recontact_reason)

            elif decision == "R":
                resolve_counter_proposal(rid, accept=False)
                print(f"[coordinator] Re-sending original options to {party_name}...")

                for party in schedule["hierarchy"]:
                    if party["party"] == party_name:
                        party["status"] = "PENDING"
                save_schedule(schedule)

                from outreach import run_outreach
                run_outreach(
                    recontact_reason="Your previous counter-proposal was not accepted. Please choose from the original options."
                )

            elif decision == "E":
                transition(rid, Status.ESCALATED, note=f"Counter-proposal from {party_name} escalated to coordinator")
                print_escalation_brief(party_name, rid, schedule)

        # --- DECLINED ---
        elif classification == "DECLINED":
            print(f"\n  ✗ {party_name} declined all options.")
            print("  Manual coordinator action required.")
            transition(rid, Status.ESCALATED, note=f"{party_name} declined all options")
            print_escalation_brief(party_name, rid, schedule)

        # --- NO_RESPONSE ---
        elif classification == "NO_RESPONSE":
            print(f"\n  ? {party_name} — automated or non-response detected.")
            print("  Sending follow-up email...")
            for party in schedule["hierarchy"]:
                if party["party"] == party_name:
                    party["status"] = "PENDING"
            save_schedule(schedule)
            from outreach import run_outreach
            run_outreach(recontact_reason="Following up on our previous scheduling request.")

        # Mark reply as processed
        processed.add(reply["reply_msg_id"])
        save_processed_replies(processed)

    state = get_request(rid)
    return {"status": state["status"], "schedule": schedule}


# ---------------------------------------------------------------------------
# Polling loop
# ---------------------------------------------------------------------------

def run_polling_loop(request_id: str = None, interval_seconds: int = 300, max_hours: int = 48):
    from reply_interpreter import run_interpreter

    start_time = datetime.now()
    max_seconds = max_hours * 3600
    poll_count = 0
    rid = request_id or load_schedule().get("request_id")

    print("\n" + "=" * 60)
    print(f"  Coordinator polling loop started")
    print(f"  Interval:  every {interval_seconds // 60} min")
    print(f"  Timeout:   {max_hours} hours")
    print(f"  Started:   {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60 + "\n")

    import time

    while True:
        elapsed = (datetime.now() - start_time).total_seconds()
        poll_count += 1

        print(f"[coordinator] Poll #{poll_count} at {datetime.now().strftime('%H:%M:%S')} "
              f"(elapsed: {int(elapsed // 60)}m)")

        current_schedule = load_schedule()
        current_rid = current_schedule.get("request_id", rid)
        if current_rid != rid:
            print(f"[coordinator] Request ID updated: {rid} → {current_rid}")
            rid = current_rid

        state = get_request(rid)

        if not state:
            print("[coordinator] No state found — exiting loop.")
            break

        current_status = state["status"]

        if current_status == Status.CONFIRMED:
            print("\n[coordinator] ✓ All parties confirmed — stopping poll loop.")
            break

        if current_status == Status.ESCALATED:
            print("\n[coordinator] ⚠ Request escalated — stopping poll loop.")
            break

        if elapsed > max_seconds:
            print(f"\n[coordinator] ⏱ Timeout after {max_hours} hours — escalating.")
            transition(rid, Status.ESCALATED, note=f"Timed out after {max_hours} hours with no full confirmation")
            print_escalation_brief("(timeout)", rid, current_schedule)
            break

        print(f"  Checking Gmail for new replies...")
        new_replies = run_interpreter(request_id=rid)

        if new_replies:
            print(f"  Found {len(new_replies)} new reply(s) — processing...")
            run_coordinator(request_id=rid)

            updated_schedule = load_schedule()
            new_rid = updated_schedule.get("request_id", rid)
            if new_rid != rid:
                print(f"[coordinator] Tracking new request ID: {rid} → {new_rid}")
                rid = new_rid
        else:
            print(f"  No new replies. Next check in {interval_seconds // 60} min.")

        time.sleep(interval_seconds)

    print(f"\n[coordinator] Loop ended after {poll_count} poll(s).")


if __name__ == "__main__":
    import sys
    interval = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    run_polling_loop(interval_seconds=interval)