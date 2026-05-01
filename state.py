import os
import json
from datetime import datetime
from enum import Enum
from typing import Optional

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json")


class Status(str, Enum):
    DRAFT = "DRAFT"                       # Constraints extracted, schedule generated, no outreach sent
    PROPOSED = "PROPOSED"                 # Outreach sent to current party, awaiting reply
    COUNTER_PROPOSED = "COUNTER_PROPOSED" # Party submitted alternative, all outreach frozen
    ESCALATED = "ESCALATED"              # Party unresponsive after follow-up, coordinator alerted
    CONFIRMED = "CONFIRMED"              # All parties confirmed, schedule locked


VALID_TRANSITIONS = {
    Status.DRAFT: [Status.PROPOSED],
    Status.PROPOSED: [Status.CONFIRMED, Status.COUNTER_PROPOSED, Status.ESCALATED],
    Status.COUNTER_PROPOSED: [Status.PROPOSED, Status.DRAFT, Status.ESCALATED],  # Accept → PROPOSED (regenerate), Reject → back to PROPOSED
    Status.ESCALATED: [Status.PROPOSED, Status.CONFIRMED],     # Coordinator resolves → re-propose or confirm
    Status.CONFIRMED: [],                                       # Terminal state
}


def load_all() -> list:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return []
    return []


def save_all(records: list):
    with open(STATE_FILE, "w") as f:
        json.dump(records, f, indent=2)


def get_request(request_id: str) -> Optional[dict]:
    for r in load_all():
        if r["request_id"] == request_id:
            return r
    return None


def get_latest() -> Optional[dict]:
    records = load_all()
    return records[-1] if records else None


def create_request(request_id: str, summary: str) -> dict:
    """Initialize a new scheduling request in DRAFT state."""
    record = {
        "request_id": request_id,
        "summary": summary,
        "status": Status.DRAFT,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "current_party_index": 0,
        "history": [
            {
                "status": Status.DRAFT,
                "timestamp": datetime.now().isoformat(),
                "note": "Request created",
            }
        ],
    }
    records = load_all()
    records.append(record)
    save_all(records)
    print(f"[state] Created request {request_id} → {Status.DRAFT}")
    return record

def reset_colocation_group(request_id: str, group_label: str, hierarchy: list, note: str = "") -> list:
    """
    Reset all CONFIRMED parties in the same colocation_group back to PENDING.
    Returns the list of parties that were reset.
    """
    records = load_all()
    record = next((r for r in records if r["request_id"] == request_id), None)

    if not record:
        raise ValueError(f"Request {request_id} not found.")

    reset_parties = []
    for party in hierarchy:
        if party.get("colocation_group") == group_label and party["status"] == "CONFIRMED":
            party["status"] = "PENDING"
            reset_parties.append(party["party"])

    record["history"].append({
        "status": record["status"],
        "timestamp": datetime.now().isoformat(),
        "note": note or f"Co-location group {group_label} reset — {', '.join(reset_parties)} returned to PENDING",
    })
    record["updated_at"] = datetime.now().isoformat()
    save_all(records)

    print(f"[state] Co-location reset: {', '.join(reset_parties)} → PENDING")
    return reset_parties

def transition(request_id: str, to_status: Status, note: str = "") -> dict:
    """
    Transition a request to a new status.
    Raises ValueError if the transition is not valid.
    """
    records = load_all()
    record = next((r for r in records if r["request_id"] == request_id), None)

    if not record:
        raise ValueError(f"Request {request_id} not found.")

    from_status = Status(record["status"])

    if to_status not in VALID_TRANSITIONS[from_status]:
        raise ValueError(
            f"Invalid transition: {from_status} → {to_status}. "
            f"Allowed: {VALID_TRANSITIONS[from_status]}"
        )

    record["status"] = to_status
    record["updated_at"] = datetime.now().isoformat()
    record["history"].append({
        "status": to_status,
        "timestamp": datetime.now().isoformat(),
        "note": note,
    })

    save_all(records)
    print(f"[state] {request_id}: {from_status} → {to_status}" + (f" ({note})" if note else ""))
    return record


def advance_party(request_id: str) -> dict:
    """
    Move to the next party in the hierarchy.
    If all parties are done, transitions to CONFIRMED.
    """
    records = load_all()
    record = next((r for r in records if r["request_id"] == request_id), None)

    if not record:
        raise ValueError(f"Request {request_id} not found.")

    record["current_party_index"] += 1
    record["updated_at"] = datetime.now().isoformat()

    save_all(records)
    print(f"[state] {request_id}: advanced to party index {record['current_party_index']}")
    return record


def set_counter_proposal(request_id: str, counter_text: str) -> dict:
    """Freeze outreach and store the counter-proposal for coordinator review."""
    records = load_all()
    record = next((r for r in records if r["request_id"] == request_id), None)

    if not record:
        raise ValueError(f"Request {request_id} not found.")

    record["counter_proposal"] = {
        "text": counter_text,
        "received_at": datetime.now().isoformat(),
        "resolved": False,
    }

    save_all(records)
    return transition(request_id, Status.COUNTER_PROPOSED, note=f"Counter-proposal received: {counter_text[:80]}")


def resolve_counter_proposal(request_id: str, accept: bool) -> dict:
    """
    Coordinator decision on a counter-proposal.
    Accept → back to DRAFT (schedule regenerated with new constraints).
    Reject → back to PROPOSED (re-send original options to party).
    """
    records = load_all()
    record = next((r for r in records if r["request_id"] == request_id), None)

    if not record:
        raise ValueError(f"Request {request_id} not found.")

    if "counter_proposal" in record:
        record["counter_proposal"]["resolved"] = True
        record["counter_proposal"]["accepted"] = accept
        save_all(records)

    if accept:
        return transition(request_id, Status.DRAFT, note="Counter-proposal accepted — regenerating schedule")
    else:
        return transition(request_id, Status.PROPOSED, note="Counter-proposal rejected — re-sending original options")


def print_state(request_id: str):
    record = get_request(request_id)
    if not record:
        print(f"No record found for {request_id}")
        return

    print(f"\n  ┌─ State ─────────────────────────────────────")
    print(f"  │  request_id:   {record['request_id']}")
    print(f"  │  status:       {record['status']}")
    print(f"  │  party_index:  {record['current_party_index']}")
    print(f"  │  updated_at:   {record['updated_at']}")
    if record.get("counter_proposal"):
        cp = record["counter_proposal"]
        print(f"  │  counter:      {cp['text'][:60]}...")
        print(f"  │  resolved:     {cp['resolved']}")
    print(f"  │  history:")
    for entry in record["history"]:
        note = f" — {entry['note']}" if entry.get("note") else ""
        print(f"  │      {entry['timestamp']}  {entry['status']}{note}")
    print(f"  └─────────────────────────────────────────────\n")


if __name__ == "__main__":
    # Quick smoke test
    rid = "test-001"
    create_request(rid, "Test scheduling request")
    transition(rid, Status.PROPOSED, note="Outreach sent to Prof. Sahlman via Kate")
    transition(rid, Status.COUNTER_PROPOSED, note="Kate replied with alternative time")
    resolve_counter_proposal(rid, accept=False)
    transition(rid, Status.CONFIRMED, note="All parties confirmed")
    print_state(rid)