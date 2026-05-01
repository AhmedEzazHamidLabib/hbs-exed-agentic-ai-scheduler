import os
import json
import re
from typing import Optional, Any

from dotenv import load_dotenv

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import BaseOutputParser
from langchain_core.messages import AIMessage, HumanMessage
from langchain_anthropic import ChatAnthropic

load_dotenv()

MODEL = "claude-sonnet-4-5"

SYSTEM_PROMPT = """You are a scheduling constraints extractor for an AI coordinator system at Harvard Business School Executive Education.

Parse whatever the coordinator provides — detailed, vague, formal, casual — and extract a constraint object.

After every reply, output a JSON block inside <constraints> tags like this:

<constraints>
{
  "summary": "One sentence dense with all key facts — every person name, room name, day, time, topic, and participant count mentioned. Used for natural language lookup later.",
  "clauses": [
    "Prof. Smith MUST teach Strategy on Day 1 AND Day 2 for 90 min each",
    "NO session CANNOT start before 09:00",
    "NO session CANNOT end after 17:00",
    "Prof. Smith CANNOT be scheduled in the afternoon",
    "Room MUST have projector AND whiteboard",
    "Prof. Smith MUST be contacted via assistant John at john@hbs.edu",
    "Prof. Smith MUST be allowed to counter-propose",
    "Prof. Smith AND Prof. Lee MUST be in the same room at the same time"
  ],
  "blocks": {
    "who": ["Prof. Smith — Strategy, Day 1 & 2", "Prof. Lee — Finance, Day 3"],
    "when": ["3 days", "09:00-17:00", "15 min break between sessions"],
    "where": ["projector and whiteboard required"],
    "contacts": ["Prof. Smith → assistant John (john@hbs.edu)", "Prof. Lee → direct (lee@hbs.edu)"],
    "counter_propose": ["Prof. Smith — allowed", "Prof. Lee — not allowed"],
    "colocation": ["Group A: Prof. Smith, Prof. Lee — must share room and time slot"]
  },
  "ambiguities": [
    "Counter-proposal allowance not specified — which parties can propose alternatives?",
    "Duration of joint faculty briefing not specified — how long is the session?"
  ],
  "more_info": [
    "Room preference not mentioned"
  ],
  "ready": false
}
</constraints>

RULES:
- Only include keys that have real values. No nulls, no empty lists.
- summary MUST always be present and MUST explicitly name every person, room, day, time, topic, and duration mentioned.
- clauses use MUST / CANNOT / AND / OR / NOT — every valid schedule must satisfy ALL clauses.
- blocks group the same info by category for downstream agents. Include counter_propose and colocation blocks once resolved.
- ambiguities = blocking gaps that MUST be resolved before scheduling can proceed.
- more_info = non-blocking nice-to-haves.
- ready: true ONLY when zero blocking ambiguities remain.
- Missing contact emails for parties that must be emailed = blocking.

SMART INFERENCE RULES — resolve these automatically, never ask about them:
- "joint session", "joint briefing", "joint faculty meeting", "joint panel", "faculty briefing", "program kickoff", or ANY phrasing implying multiple people in the same room at the same time → co-location RESOLVED automatically. Set colocation_group, add colocation clause, do NOT add to ambiguities.
- "both allowed to counter-propose", "all parties may counter-propose", "both can counter-propose", or any equivalent phrasing → counter-proposal RESOLVED for all parties. Do NOT add to ambiguities.
- Party described as assistant or contact for a professor → infer contact_via = "assistant" automatically.
- Same room mentioned for multiple sessions on the same day → infer shared room automatically.

BLOCKING AMBIGUITY RULES — add to ambiguities only when genuinely unclear:
- Multiple parties present AND counter-proposal allowance NOT stated in any form → BLOCKING: "Counter-proposal allowance not specified — which parties, if any, are allowed to propose alternative times?"
- Multiple parties present AND co-location NOT implied by session type or wording → BLOCKING: "Co-location not specified — which parties must be in the same room together, if any?"
- A joint or shared session is mentioned BUT its duration is not stated → BLOCKING: "Duration of [session name] not specified — how long is this session?"
- Any session mentioned without a start time when scheduling depends on it → BLOCKING: "Start time for [session] not specified."
- NEVER ask about something clearly stated or strongly implied. NEVER invent ambiguities.

CONVERSATION BEHAVIOR:
After the first message, ask ALL blocking questions at once in a single numbered list. Never split across turns.

Format:
"I've extracted the constraints. Before proceeding I need to clarify:
1. [question]
2. [question]

Answer what you can — or say go ahead and I'll proceed with what I have."

PRIORITY RULES:
1. You are a constraint extraction engine, not a general assistant.
2. Topic is non-blocking unless the coordinator says scheduling depends on it.
3. Participant count is non-blocking unless it affects room assignment.
4. Session duration IS blocking — the scheduler cannot generate accurate end times without it.
5. After the first follow-up round, NEVER ask additional questions.
6. On the second response, say "I have everything I need — let me know if you want to add anything, or I'll proceed." Then set ready: true.
7. If the coordinator says "go ahead", "proceed", "just do it", or similar → set ready: true immediately, no questions.
8. Counter-proposal allowance is BLOCKING when multiple parties are present AND genuinely ambiguous. Never ask if already stated in any form.
9. Co-location is BLOCKING when multiple parties are present AND genuinely ambiguous. Never ask if a joint session was mentioned.
10. Duration of any named session is BLOCKING if not specified and that session must be scheduled.
"""


class ConstraintsParser(BaseOutputParser[dict]):
    def parse(self, text: str) -> dict[str, Any]:
        match = re.search(r"<constraints>\s*(\{.*\})\s*</constraints>", text, re.DOTALL)
        constraints = None
        if match:
            try:
                constraints = json.loads(match.group(1))
            except json.JSONDecodeError:
                constraints = None

        clean_reply = re.sub(r"<constraints>\s*\{.*\}\s*</constraints>", "", text, flags=re.DOTALL).strip()
        return {"reply": clean_reply, "constraints": constraints, "raw": text}


prompt = ChatPromptTemplate.from_messages(
    [
        ("system", SYSTEM_PROMPT),
        MessagesPlaceholder(variable_name="history"),
        ("human", "{{ user_input }}")
    ],
    template_format="jinja2"
)

model = ChatAnthropic(
    model=MODEL,
    api_key=os.environ.get("ANTHROPIC_API_KEY"),
    temperature=0.1,
)

parser = ConstraintsParser()
chain = prompt | model | parser


def print_constraints(c: dict):
    print("\n  ┌─ Constraints ──────────────────────────────")
    if c.get("clauses"):
        print("  │  [clauses]")
        for clause in c["clauses"]:
            print(f"  │      • {clause}")
    if c.get("blocks"):
        print("  │  [blocks]")
        for category, items in c["blocks"].items():
            print(f"  │      {category}:")
            for item in items:
                print(f"  │          - {item}")
    if c.get("ambiguities"):
        print("  │  [ambiguities — blocking]")
        for a in c["ambiguities"]:
            print(f"  │      ⚠  {a}")
    if c.get("more_info"):
        print("  │  [more info — non-blocking]")
        for m in c["more_info"]:
            print(f"  │      ?  {m}")
    ready = c.get("ready", False)
    print(f"  │  ready: {'✓ YES' if ready else '✗ NO'}")
    print("  └────────────────────────────────────────────\n")


def get_multiline_input() -> str:
    print("[You] (press Enter twice to send):")
    lines = []
    while True:
        line = input()
        if line == "":
            if lines:
                break
        else:
            lines.append(line)
    return "\n".join(lines).strip()


def run_parser_langchain(initial_input: Optional[str] = None) -> dict:
    history = []
    current_constraints = {}

    print("\n" + "=" * 60)
    print("  HBS Executive Education — Scheduling Coordinator")
    print("  Describe your program requirements in plain text.")
    print("  Commands: 'show' = print constraints, 'done' = finish")
    print("=" * 60 + "\n")

    print("[Coordinator] Hi — describe your scheduling requirements and I'll extract everything needed to generate schedule options.\n")

    first_input = initial_input

    while True:
        if first_input:
            user_input = first_input.strip()
            first_input = None
            print(f"[You] {user_input}\n")
        else:
            user_input = get_multiline_input()

        if not user_input:
            continue

        lowered = user_input.lower()

        if lowered == "show":
            print_constraints(current_constraints) if current_constraints else print("  No constraints yet.\n")
            continue

        if lowered in ("done", "quit", "exit"):
            print("\nSession ended.")
            break

        result = chain.invoke({"history": history, "user_input": user_input})

        reply = result["reply"]
        constraints = result["constraints"]
        raw = result["raw"]

        history.append(HumanMessage(content=user_input))
        history.append(AIMessage(content=raw))

        if constraints:
            current_constraints = constraints

        print(f"\n[Coordinator] {reply}\n")

        if current_constraints:
            print_constraints(current_constraints)

        if current_constraints.get("ready"):
            constraints_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "constraints.json")
            with open(constraints_file, "w") as f:
                json.dump(current_constraints, f, indent=2)
            print("Saved to constraints.json\n")
            print("=" * 60)
            print("  ✓ Constraints complete. Handing off to scheduler.")
            print("=" * 60 + "\n")
            return current_constraints

    return current_constraints


if __name__ == "__main__":
    import sys
    initial = None
    if len(sys.argv) > 1:
        try:
            with open(sys.argv[1], "r") as f:
                initial = f.read().strip()
            print(f"Loaded input from {sys.argv[1]}\n")
        except FileNotFoundError:
            print(f"File not found: {sys.argv[1]}. Starting interactive.\n")

    result = run_parser_langchain(initial_input=initial)
    if result:
        with open("constraints.json", "w") as f:
            json.dump(result, f, indent=2)
        print("Saved to constraints.json\n")
        print(json.dumps(result, indent=2))