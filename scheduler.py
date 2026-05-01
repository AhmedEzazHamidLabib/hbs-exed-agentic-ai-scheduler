import os
import json
import uuid
from datetime import datetime
from typing import Any
import re

from dotenv import load_dotenv
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import BaseOutputParser
from langchain_anthropic import ChatAnthropic

load_dotenv()
SAVE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schedule_options.json")

MODEL = "claude-sonnet-4-5"

SYSTEM_PROMPT = """You are a scheduling coordinator for Harvard Business School Executive Education.

You receive scheduling constraints and must:
1. Generate 2-3 concrete, feasible schedule options
2. Extract the full contact hierarchy from the constraints

Return ONLY a raw JSON object — no preamble, no explanation, no markdown, no code fences. Just the JSON.

Format:
{
  "hierarchy": [
    {
      "party": "Prof. Sahlman",
      "role": "instructor",
      "contact_name": "Kate",
      "contact_email": "kate@hbs.edu",
      "contact_via": "assistant",
      "sessions": ["Day 1 — Venture Capital"],
      "status": "PENDING",
      "can_counter_propose": false,
      "colocation_group": null
    }
  ],
  "options": [
    {
      "option": "A",
      "sessions": [
        {
          "day": "Day 1",
          "instructor": "Prof. Sahlman",
          "topic": "Venture Capital",
          "room": "Aldrich 112",
          "start": "09:00",
          "end": "10:30",
          "duration_min": 90
        }
      ]
    }
  ]
}

HIERARCHY RULES:
- Extract every person who needs to be contacted from the constraints
- Order by seniority: dept chair first if mentioned, then professors via assistants, then professors directly, then facilities/room coordinators last
- contact_via is "assistant" if contacted through someone else, "direct" otherwise
- contact_name is the assistant name if via assistant, otherwise the professor's name
- sessions lists which sessions this party is responsible for confirming — include ALL sessions for that party including joint sessions
- Include ALL parties — if a room coordinator is mentioned, include them too
- CONTACT ORDER: If an explicit contact order is stated, set the first party PENDING and all others WAITING. If no order is stated, set ALL parties PENDING — they will all be contacted simultaneously.
- COUNTER-PROPOSAL: Set can_counter_propose true only if explicitly granted in the constraints. Default false.
- COLOCATION: Assign a colocation_group label (e.g. "A", "B") to parties that must be physically present together. Use null if no colocation constraint. If any party in a colocation group counter-proposes after another confirmed, all confirmed parties in that group reset to PENDING.

SCHEDULE RULES:
- Satisfy ALL clauses simultaneously — no exceptions
- Each clause that specifies a session MUST generate a separate session block — never merge clauses into one session
- If 3 session clauses exist, each option must contain exactly 3 session blocks ordered chronologically
- A joint session shared by multiple instructors must appear as its own session block with all instructor names listed
- Each session block must have: day, instructor, topic, room, start, end, duration_min
- Each option must be fully concrete — exact day, start, end, room, instructor, topic
- Options must differ meaningfully (different times, not just labels)
- If a time preference exists, make that Option A
- If only 2 meaningful options exist, output 2 — never force a 3rd that violates constraints
- Sessions on the same day must not overlap and must respect break requirements
- Parties in the same colocation_group MUST be scheduled in the same room at the same time
- If all time/date constraints are fully pinned (exact day AND exact start time for all sessions), generate only ONE option
- Never invent session details not present in the clauses
"""


class ScheduleParser(BaseOutputParser[dict]):
    def parse(self, text: str) -> dict[str, Any]:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)
            cleaned = cleaned.strip()
        try:
            return {"schedule": json.loads(cleaned), "raw": text}
        except json.JSONDecodeError as e:
            print(f"JSON parse error: {e}")
            print(f"Raw output:\n{text}")
            return {"schedule": None, "raw": text}


prompt = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_PROMPT),
    ("human",
     """Here are the scheduling constraints. Generate concrete schedule options and extract the full contact hierarchy.

SUMMARY:
{{ summary }}

CLAUSES (all must be satisfied — one session block per clause):
{{ clauses }}

BLOCKS:
{{ blocks }}

Return only the JSON object now.""")
], template_format="jinja2")

model = ChatAnthropic(
    model=MODEL,
    api_key=os.environ.get("ANTHROPIC_API_KEY"),
    temperature=0.3,
)

parser = ScheduleParser()
chain = prompt | model | parser


def load_all() -> list:
    if os.path.exists(SAVE_FILE):
        with open(SAVE_FILE, "r") as f:
            try:
                data = json.load(f)
                return data if isinstance(data, list) else [data]
            except json.JSONDecodeError:
                return []
    return []


def save_all(records: list):
    with open(SAVE_FILE, "w") as f:
        json.dump(records, f, indent=2)


def run_scheduler_langchain(constraints_file: str) -> dict:
    with open(constraints_file, "r") as f:
        constraints = json.load(f)

    result = chain.invoke({
        "summary": constraints.get("summary", ""),
        "clauses": json.dumps(constraints.get("clauses", []), indent=2),
        "blocks": json.dumps(constraints.get("blocks", {}), indent=2),
    })

    schedule = result["schedule"]
    if not schedule:
        print("Could not parse schedule.")
        return {}

    output = {
        "request_id": constraints.get("request_id") or constraints.get("id", str(uuid.uuid4())[:8]),
        "generated_at": datetime.now().isoformat(),
        "summary": constraints.get("summary", ""),
        "status": "PENDING_CONFIRMATION",
        "hierarchy": schedule.get("hierarchy", []),
        "options": schedule.get("options", []),
        "constraints": constraints,
    }

    # Override can_counter_propose from constraints blocks
    counter_propose_block = constraints.get("blocks", {}).get("counter_propose", [])
    allowed_parties = [
        line.split("—")[0].strip().lower()
        for line in counter_propose_block
        if "allowed" in line.lower() and "not allowed" not in line.lower()
    ]
    for party in output["hierarchy"]:
        party["can_counter_propose"] = any(
            allowed in party["party"].lower()
            for allowed in allowed_parties
        )

    records = load_all()
    records.append(output)
    save_all(records)
    print(f"Saved to schedule_options.json ({len(records)} total records)\n")

    return output


if __name__ == "__main__":
    result = run_scheduler_langchain("constraints.json")
    if result:
        print(json.dumps(result, indent=2))