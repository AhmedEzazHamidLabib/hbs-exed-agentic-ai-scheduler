import os
import json
import base64
from datetime import datetime
from typing import Any
from email.mime.text import MIMEText
import re

from dotenv import load_dotenv
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import BaseOutputParser
from langchain_anthropic import ChatAnthropic

from state import Status, get_request, get_latest, transition, create_request

load_dotenv()

MODEL = "claude-sonnet-4-5"

CREDENTIALS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "credentials.json")
TOKEN_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "token.json")
SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
]

SYSTEM_PROMPT = """You are a faculty scheduling coordinator for Harvard Business School Executive Education.

You will receive:
- The scheduling request summary
- The contact details for ONE specific faculty member or their assistant
- The session options relevant to that party only
- Whether this faculty member is allowed to counter-propose
- Whether this is a first contact or a re-contact (and why)

Write a professional, formal outreach email appropriate for Harvard Business School faculty communication.

Return ONLY a raw JSON object — no preamble, no explanation, no markdown, no code fences. Just the JSON.

Format:
{
  "to": "kate@hbs.edu",
  "subject": "Session Confirmation Request — Prof. Sahlman, Venture Capital Module",
  "body": "Full email body here..."
}

EMAIL RULES:
- If contacting via assistant: address the assistant by name and reference their professor (e.g. "Dear Kate, I am writing regarding Prof. Sahlman's session...")
- If contacting directly: address the professor formally (e.g. "Dear Prof. Sahlman,")
- Include only the sessions this party is responsible for confirming
- If can_counter_propose is true: invite the faculty member to confirm one of the options or propose an alternative time
- If can_counter_propose is false: request confirmation or declination only — do NOT invite alternatives
- Keep it under 200 words — concise and professional
- Tone must be formal and respectful, appropriate for senior HBS faculty
- Sign off as: HBS Executive Education Scheduling Coordinator, Harvard Business School

BODY FORMAT — always follow this exact structure, no exceptions:
1. Opening line: one sentence addressing the recipient and stating the purpose
2. Blank line
3. If only ONE option exists, present sessions directly without any "Option A:" label
   If MULTIPLE options exist, label each group with "Option A:", "Option B:", etc.
   Each session block always uses this exact field order with each field on its own line:
   Session: [topic]
   Date: [day]
   Time: [start] — [end] ([duration] min)
   Room: [room]
4. Blank line between each session block
5. One closing line stating what action is required
6. Blank line
7. Sign-off:
   HBS Executive Education Scheduling Coordinator
   Harvard Business School

FORMATTING RULES:
- Never use markdown bold (**text**), bullet points, or dashes for session fields
- Never combine session fields on one line — each field must be on its own line
- Always use plain text only
- Always use the exact field labels in this order: Session, Date, Time, Room
- Never add extra fields or omit any of the four
- Never write "Option A:" when there is only one option

CRITICAL FORMATTING RULE:
Each field in a session block MUST be on its own line separated by \\n in the JSON body string.
Never put Session, Date, Time, and Room on the same line.
Every session must have its own complete block with all four fields.

EXAMPLE OUTPUT — single option with multiple sessions (body field only):
Dear Prof. Eisenmann,

I am writing on behalf of HBS Executive Education to confirm your availability for the following sessions on Monday April 28th.

Session: Joint Faculty Briefing
Date: Monday April 28th
Time: 09:00 — 11:00 (120 min)
Room: Aldrich 112

Session: Entrepreneurship Strategy
Date: Monday April 28th
Time: 12:30 — 14:00 (90 min)
Room: Aldrich 112

Please reply to confirm or propose an alternative time at your earliest convenience.

HBS Executive Education Scheduling Coordinator
Harvard Business School

EXAMPLE OUTPUT — multiple options (body field only):
Dear Kate,

I am writing on behalf of HBS Executive Education to request confirmation of Prof. Sahlman's availability for the following Venture Capital module session.

Option A:
Session: Venture Capital — Deal Structuring
Date: Monday April 28th
Time: 09:00 — 10:30 (90 min)
Room: Aldrich 112

Option B:
Session: Venture Capital — Deal Structuring
Date: Monday April 28th
Time: 14:00 — 15:30 (90 min)
Room: Aldrich 112

Please reply at your earliest convenience to confirm one of the above options or propose an alternative time.

HBS Executive Education Scheduling Coordinator
Harvard Business School

RE-CONTACT RULES (only apply when is_recontact is true):
- Open by acknowledging prior contact or the faculty member's previous confirmation
- Briefly and professionally explain the reason for re-contact
- Present updated sessions using the same session block format above
- Maintain a formal, apologetic but efficient tone
- Subject line must include "Updated:" to distinguish from the original outreach

RE-CONTACT EXAMPLE (body field only):
Dear Kate,

Thank you for Prof. Sahlman's confirmation of the earlier session time. We regret to inform you that a scheduling conflict has arisen requiring us to present revised options for his consideration.

Option A:
Session: Venture Capital — Deal Structuring
Date: Tuesday April 29th
Time: 10:00 — 11:30 (90 min)
Room: Aldrich 112

We sincerely apologize for the inconvenience and would be grateful for Prof. Sahlman's earliest response.

HBS Executive Education Scheduling Coordinator
Harvard Business School
"""


class EmailParser(BaseOutputParser[dict]):
    def parse(self, text: str) -> dict[str, Any]:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)
            cleaned = cleaned.strip()
        try:
            return {"email": json.loads(cleaned), "raw": text}
        except json.JSONDecodeError as e:
            print(f"JSON parse error: {e}")
            print(f"Raw output:\n{text}")
            return {"email": None, "raw": text}


prompt = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_PROMPT),
    ("human",
     """Generate the outreach email for this party.

SUMMARY:
{{ summary }}

PARTY:
{{ party }}

THEIR SESSIONS ACROSS OPTIONS:
{{ sessions }}

IS RE-CONTACT: {{ is_recontact }}
RE-CONTACT REASON: {{ recontact_reason }}

Return only the JSON object now.""")
], template_format="jinja2")

model = ChatAnthropic(
    model=MODEL,
    api_key=os.environ.get("ANTHROPIC_API_KEY"),
    temperature=0.3,
)

parser = EmailParser()
chain = prompt | model | parser

EMAILS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "emails_options.json")


def load_emails() -> list:
    if os.path.exists(EMAILS_FILE):
        with open(EMAILS_FILE, "r") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return []
    return []


def save_emails(records: list):
    with open(EMAILS_FILE, "w") as f:
        json.dump(records, f, indent=2)


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


def get_party_sessions(party: dict, options: list) -> list:
    party_name = party["party"]
    relevant = []
    for option in options:
        option_sessions = [
            s for s in option["sessions"]
            if party_name.lower() in s.get("instructor", "").lower()
        ]
        if option_sessions:
            relevant.append({"option": option["option"], "sessions": option_sessions})
    return relevant


def get_previous_status(party_name: str, request_id: str) -> str:
    all_emails = load_emails()
    prior = [
        e for e in all_emails
        if e.get("request_id") == request_id and e.get("party") == party_name and e.get("sent")
    ]
    if not prior:
        return None
    return prior[-1].get("sent_at")


def print_email(email: dict, party: dict, index: int, is_recontact: bool = False):
    can_cp = party.get("can_counter_propose", False)
    print(f"\n  ┌─ Email {index} {'[RE-CONTACT]' if is_recontact else '[FIRST CONTACT]'} ──────────────────")
    print(f"  │  TO:              {email['to']}")
    print(f"  │  PARTY:           {party['party']} (via {party['contact_via']})")
    print(f"  │  CAN COUNTER:     {'YES' if can_cp else 'NO'}")
    print(f"  │  COLOCATION:      {party.get('colocation_group') or 'none'}")
    print(f"  │  SUBJECT:         {email['subject']}")
    print(f"  │  ──────────────────────────────────────────")
    for line in email["body"].split("\n"):
        print(f"  │  {line}")
    print(f"  └────────────────────────────────────────────────\n")


def send_via_gmail(service, email: dict) -> dict:
    try:
        msg = MIMEText(email["body"])
        msg["To"] = email["to"]
        msg["Subject"] = email["subject"]

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        result = service.users().messages().send(userId="me", body={"raw": raw}).execute()

        msg_detail = service.users().messages().get(
            userId="me", id=result["id"], format="metadata",
            metadataHeaders=["Message-ID"]
        ).execute()

        headers = msg_detail.get("payload", {}).get("headers", [])
        message_id = next(
            (h["value"] for h in headers if h["name"].lower() == "message-id"), None
        )

        print(f"  [outreach] ✓ Sent to {email['to']} (message_id: {message_id})")
        return {"sent": True, "gmail_id": result["id"], "message_id": message_id}

    except Exception as e:
        print(f"  [outreach] ✗ Failed to send to {email['to']}: {e}")
        return {"sent": False, "gmail_id": None, "message_id": None}


def run_outreach(schedule_options_file: str = None, recontact_reason: str = None) -> list:
    if schedule_options_file:
        with open(schedule_options_file, "r") as f:
            data = json.load(f)
        schedule = data[-1] if isinstance(data, list) else data
    else:
        from scheduler import SAVE_FILE
        with open(SAVE_FILE, "r") as f:
            records = json.load(f)
        schedule = records[-1]

    rid = schedule["request_id"]
    summary = schedule["summary"]
    hierarchy = schedule["hierarchy"]
    options = schedule["options"]

    state = get_request(rid)
    if not state:
        state = create_request(rid, summary)

    pending_parties = [p for p in hierarchy if p["status"] == "PENDING"]
    if not pending_parties:
        print("[outreach] No PENDING parties found — nothing to send.")
        return []

    generated = []
    for party in pending_parties:
        previous_sent_at = get_previous_status(party["party"], rid)
        is_recontact = previous_sent_at is not None or recontact_reason is not None

        if recontact_reason:
            reason = recontact_reason
        elif previous_sent_at:
            all_emails_history = load_emails()
            previously_confirmed = any(
                e.get("request_id") == rid and e.get("party") == party["party"]
                and e.get("sent") and not e.get("is_recontact")
                for e in all_emails_history
            )
            reason = (
                "Another faculty member has proposed a schedule change requiring updated options."
                if previously_confirmed
                else f"Following up on our previous outreach on {previous_sent_at[:10]}."
            )
        else:
            reason = "N/A"

        print(f"\n[outreach] Generating {'re-contact' if is_recontact else 'first contact'} email for {party['party']}...")

        party_sessions = get_party_sessions(party, options)
        if not party_sessions:
            party_sessions = options

        result = chain.invoke({
            "summary": summary,
            "party": json.dumps(party, indent=2),
            "sessions": json.dumps(party_sessions, indent=2),
            "is_recontact": str(is_recontact),
            "recontact_reason": reason,
        })

        email = result["email"]
        if not email:
            print(f"[outreach] Could not generate email for {party['party']}")
            continue

        generated.append({"party": party, "email": email, "is_recontact": is_recontact, "recontact_reason": reason})

    if not generated:
        print("[outreach] No emails generated.")
        return []

    print("\n" + "=" * 60)
    print("  OUTREACH PREVIEW — Review before sending")
    print("=" * 60)
    for i, item in enumerate(generated, 1):
        print_email(item["email"], item["party"], i, item["is_recontact"])

    print("=" * 60)
    confirm = input("  Type CONFIRM to send all emails, or anything else to abort: ").strip()
    print("=" * 60 + "\n")

    if confirm != "CONFIRM":
        print("[outreach] Aborted — no emails sent.")
        return []

    print("[outreach] Authenticating with Gmail...")
    service = get_gmail_service()

    sent_emails = []
    for item in generated:
        send_result = send_via_gmail(service, item["email"])
        record = {
            "request_id": rid,
            "sent_at": datetime.now().isoformat(),
            "party": item["party"]["party"],
            "contact_email": item["party"]["contact_email"],
            "can_counter_propose": item["party"].get("can_counter_propose", False),
            "colocation_group": item["party"].get("colocation_group"),
            "is_recontact": item["is_recontact"],
            "recontact_reason": item["recontact_reason"],
            "sent": send_result["sent"],
            "gmail_id": send_result["gmail_id"],
            "message_id": send_result["message_id"],
            "email": item["email"],
        }
        sent_emails.append(record)

    all_emails = load_emails()
    all_emails.extend(sent_emails)
    save_emails(all_emails)
    print(f"\n[outreach] Saved {len(sent_emails)} email record(s) to emails_options.json")

    state = get_request(rid)
    if state and state["status"] == Status.DRAFT:
        transition(rid, Status.PROPOSED, note=f"Outreach sent to {sent_emails[0]['party']}")
    else:
        print(f"[outreach] State already {state['status']} — skipping transition")

    return sent_emails


if __name__ == "__main__":
    results = run_outreach()
    if results:
        print(json.dumps(results, indent=2))