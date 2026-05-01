import os
import json
import base64
from datetime import datetime
from typing import Any, Optional
import re

from dotenv import load_dotenv
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import BaseOutputParser
from langchain_anthropic import ChatAnthropic

load_dotenv()

MODEL = "claude-sonnet-4-5"

CREDENTIALS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "credentials.json")
TOKEN_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "token.json")
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

EMAILS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "emails_options.json")
REPLIES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "replies.json")

SYSTEM_PROMPT = """You are a reply interpreter for an AI scheduling coordinator system at Harvard Business School Executive Education.

You will receive:
- The original email sent to a faculty member or their assistant
- The faculty member's reply (raw email text)
- Whether this party is allowed to counter-propose
- The current scheduling constraints

Classify the reply and extract any new constraints if applicable.

Return ONLY a raw JSON object — no preamble, no explanation, no markdown, no code fences.

Format:
{
  "classification": "CONFIRMED" | "COUNTER_PROPOSED" | "NO_RESPONSE" | "DECLINED",
  "confidence": "HIGH" | "MEDIUM" | "LOW",
  "summary": "One sentence summary of what the party said",
  "confirmed_option": "A",
  "new_constraints": {
    "override_clauses": [
      "Meeting MUST be on April 29th at 10:00 for 90 minutes in Aldrich 112"
    ],
    "override_when": ["April 29th starting at 10:00"],
    "notes": "Faculty member proposes April 29th at 10am instead"
  }
}

CLASSIFICATION RULES — interpret natural language generously and intelligently:

CONFIRMED — classify as confirmed if the reply indicates agreement in any form, including:
- Direct: "confirmed", "works for me", "I'll be there", "that's fine", "sounds good", "perfect"
- Indirect: "I can make it", "that works", "no problem", "happy to attend", "see you then"
- Casual: "yep", "sure", "ok", "great", "absolutely", "definitely"
- With option: "Option A works", "let's do the morning slot", "the 9am is fine"
- Even if the reply has additional commentary — if the core message is agreement, classify as CONFIRMED

COUNTER_PROPOSED — classify as counter-proposed if the reply proposes a different time/date/room.
Only valid if can_counter_propose is true. If false, classify as DECLINED.
- Direct: "Can we do Tuesday instead?", "I'd prefer 2pm", "Could we move to Burden Hall?"
- Indirect: "I have a conflict that day, what about...", "Would it be possible to reschedule to..."
- Casual: "That doesn't work, how about 10am?", "Can you make it later?"

DECLINED — classify as declined if:
- Explicit refusal: "I cannot attend", "I'm unavailable", "I must decline"
- Proposes changes but can_counter_propose is false
- States they are completely unavailable with no alternative offered

NO_RESPONSE — classify as no response if:
- Out of office auto-reply
- Automated system message
- Reply clearly unrelated to the scheduling request
- Garbled or empty reply

IMPORTANT INTELLIGENCE RULES:
- Read the FULL reply, not just the first line — context matters
- If someone says "that day doesn't work" but then confirms another option, classify as CONFIRMED for that option
- If someone asks a clarifying question but ultimately agrees, classify as CONFIRMED
- Err on the side of CONFIRMED when the reply is ambiguous but positive in tone
- For counter-proposals: extract the SPECIFIC date/time/room proposed, not just that they want to change

new_constraints rules (only include if COUNTER_PROPOSED):
- override_clauses MUST use MUST/CANNOT vocabulary as hard constraints
- If a specific date and time are proposed: "Meeting MUST be on [date] at [time] for [duration] in [room]"
- If only time changes: "Meeting MUST start at [time]"
- override_when must reflect the new when block
- Be precise — extract exactly what was proposed
- confidence: HIGH if unambiguous, MEDIUM if mostly clear, LOW if very vague
"""


class ReplyParser(BaseOutputParser[dict]):
    def parse(self, text: str) -> dict[str, Any]:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)
            cleaned = cleaned.strip()
        try:
            return {"result": json.loads(cleaned), "raw": text}
        except json.JSONDecodeError as e:
            print(f"JSON parse error: {e}")
            print(f"Raw output:\n{text}")
            return {"result": None, "raw": text}


prompt = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_PROMPT),
    ("human",
     """Classify this reply.

ORIGINAL EMAIL SENT:
{{ original_email }}

PARTY DETAILS:
{{ party }}

CAN COUNTER PROPOSE: {{ can_counter_propose }}

REPLY TEXT:
{{ reply_text }}

CURRENT CONSTRAINTS SUMMARY:
{{ constraints_summary }}

Return only the JSON object now.""")
], template_format="jinja2")

model = ChatAnthropic(
    model=MODEL,
    api_key=os.environ.get("ANTHROPIC_API_KEY"),
    temperature=0.1,
)

parser = ReplyParser()
chain = prompt | model | parser


def get_gmail_service():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def get_email_body(service, msg_id: str) -> str:
    try:
        msg = service.users().messages().get(userId="me", id=msg_id, format="full").execute()
        payload = msg.get("payload", {})

        def extract_text(payload):
            if payload.get("mimeType") == "text/plain":
                data = payload.get("body", {}).get("data", "")
                if data:
                    return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
            for part in payload.get("parts", []):
                result = extract_text(part)
                if result:
                    return result
            return ""

        return extract_text(payload)
    except Exception as e:
        print(f"  [interpreter] Could not fetch email body: {e}")
        return ""


def get_header(service, msg_id: str, header_name: str) -> Optional[str]:
    try:
        msg = service.users().messages().get(
            userId="me", id=msg_id, format="metadata",
            metadataHeaders=[header_name]
        ).execute()
        headers = msg.get("payload", {}).get("headers", [])
        return next((h["value"] for h in headers if h["name"].lower() == header_name.lower()), None)
    except Exception:
        return None


def poll_for_replies(service, sent_records: list) -> list:
    id_to_record = {
        r["message_id"]: r
        for r in sent_records
        if r.get("message_id") and r.get("sent")
    }

    if not id_to_record:
        print("[interpreter] No sent message IDs to match against.")
        return []

    print(f"[interpreter] Polling inbox for replies to {len(id_to_record)} sent emails...")

    results = service.users().messages().list(
        userId="me", labelIds=["INBOX"], maxResults=50,
    ).execute()

    messages = results.get("messages", [])
    matched = []

    for msg in messages:
        in_reply_to = get_header(service, msg["id"], "In-Reply-To")
        if in_reply_to and in_reply_to in id_to_record:
            sent_record = id_to_record[in_reply_to]
            body = get_email_body(service, msg["id"])
            matched.append({
                "sent_record": sent_record,
                "reply_msg_id": msg["id"],
                "reply_body": body,
            })
            print(f"  [interpreter] Found reply from {sent_record['party']} (msg: {msg['id'][:12]}...)")

    if not matched:
        print("[interpreter] No replies found yet.")

    return matched


def merge_constraints(existing: dict, new_constraints: dict) -> dict:
    merged = json.loads(json.dumps(existing))
    changes = []

    if new_constraints.get("override_clauses"):
        time_keywords = [
            "start", "end", "before", "after", "morning", "afternoon",
            "08:00", "09:00", "10:00", "11:00", "12:00", "13:00", "14:00", "15:00", "16:00", "17:00", "18:00",
            "sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday",
            "january", "february", "march", "april", "may", "june",
            "july", "august", "september", "october", "november", "december"
        ]
        original_clauses = merged.get("clauses", [])
        kept_clauses = [
            c for c in original_clauses
            if not any(kw in c.lower() for kw in time_keywords)
        ]
        new_clauses = kept_clauses + new_constraints["override_clauses"]
        changes.append(f"Replaced {len(original_clauses) - len(kept_clauses)} time clauses with {len(new_constraints['override_clauses'])} new ones")
        merged["clauses"] = new_clauses

    if new_constraints.get("override_when"):
        old_when = merged.get("blocks", {}).get("when", [])
        merged.setdefault("blocks", {})["when"] = new_constraints["override_when"]
        changes.append(f"Replaced when block: {old_when} → {new_constraints['override_when']}")

    if new_constraints.get("notes"):
        merged["summary"] = merged.get("summary", "") + f" [UPDATED: {new_constraints['notes']}]"
        changes.append(f"Added note: {new_constraints['notes']}")

    merged["_merge_log"] = {"merged_at": datetime.now().isoformat(), "changes": changes}
    return merged


def load_replies() -> list:
    if os.path.exists(REPLIES_FILE):
        with open(REPLIES_FILE, "r") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return []
    return []


def save_replies(records: list):
    with open(REPLIES_FILE, "w") as f:
        json.dump(records, f, indent=2)


def load_emails() -> list:
    if os.path.exists(EMAILS_FILE):
        with open(EMAILS_FILE, "r") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return []
    return []


def run_interpreter(request_id: str = None) -> list:
    all_emails = load_emails()

    if request_id:
        sent_records = [e for e in all_emails if e.get("request_id") == request_id and e.get("sent")]
    else:
        sent_records = [e for e in all_emails if e.get("sent")]

    if not sent_records:
        print("[interpreter] No sent emails found to check replies for.")
        return []

    constraints = {}
    constraints_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "constraints.json")
    if os.path.exists(constraints_file):
        with open(constraints_file, "r") as f:
            constraints = json.load(f)

    print("[interpreter] Authenticating with Gmail...")
    service = get_gmail_service()

    matched_replies = poll_for_replies(service, sent_records)
    if not matched_replies:
        return []

    results = []
    already_processed = {r["reply_msg_id"] for r in load_replies()}

    for match in matched_replies:
        sent_record = match["sent_record"]
        reply_msg_id = match["reply_msg_id"]
        reply_body = match["reply_body"]

        if reply_msg_id in already_processed:
            print(f"  [interpreter] Skipping already processed reply {reply_msg_id[:12]}...")
            continue

        print(f"\n[interpreter] Classifying reply from {sent_record['party']}...")
        print(f"  Reply preview: {reply_body[:100].strip()}...")

        result = chain.invoke({
            "original_email": json.dumps(sent_record["email"], indent=2),
            "party": json.dumps({
                "party": sent_record["party"],
                "contact_email": sent_record["contact_email"],
                "colocation_group": sent_record.get("colocation_group"),
            }, indent=2),
            "can_counter_propose": str(sent_record.get("can_counter_propose", False)),
            "reply_text": reply_body,
            "constraints_summary": constraints.get("summary", "No constraints available"),
        })

        classification = result["result"]
        if not classification:
            print(f"  [interpreter] Could not classify reply from {sent_record['party']}")
            continue

        print(f"\n  ┌─ Classification ────────────────────────────")
        print(f"  │  PARTY:          {sent_record['party']}")
        print(f"  │  RESULT:         {classification['classification']}")
        print(f"  │  CONFIDENCE:     {classification['confidence']}")
        print(f"  │  SUMMARY:        {classification['summary']}")
        if classification.get("confirmed_option"):
            print(f"  │  OPTION:         {classification['confirmed_option']}")
        if classification.get("new_constraints"):
            nc = classification["new_constraints"]
            print(f"  │  NEW CLAUSES:    {nc.get('override_clauses', [])}")
            print(f"  │  NEW WHEN:       {nc.get('override_when', [])}")
            print(f"  │  NOTES:          {nc.get('notes', '')}")
        print(f"  └────────────────────────────────────────────\n")

        merged_constraints = None
        if classification["classification"] == "COUNTER_PROPOSED" and classification.get("new_constraints"):
            print(f"[interpreter] Merging counter-proposal constraints...")
            merged_constraints = merge_constraints(constraints, classification["new_constraints"])
            print(f"  Changes: {merged_constraints.get('_merge_log', {}).get('changes', [])}")

        record = {
            "request_id": sent_record["request_id"],
            "party": sent_record["party"],
            "contact_email": sent_record["contact_email"],
            "can_counter_propose": sent_record.get("can_counter_propose", False),
            "colocation_group": sent_record.get("colocation_group"),
            "reply_msg_id": reply_msg_id,
            "replied_at": datetime.now().isoformat(),
            "classification": classification["classification"],
            "confidence": classification["confidence"],
            "summary": classification["summary"],
            "confirmed_option": classification.get("confirmed_option"),
            "new_constraints": classification.get("new_constraints"),
            "merged_constraints": merged_constraints,
            "reply_body": reply_body,
        }
        results.append(record)

    if results:
        all_replies = load_replies()
        all_replies.extend(results)
        save_replies(all_replies)
        print(f"[interpreter] Saved {len(results)} reply record(s) to replies.json")

    return results


if __name__ == "__main__":
    results = run_interpreter()
    if results:
        print(json.dumps(results, indent=2))