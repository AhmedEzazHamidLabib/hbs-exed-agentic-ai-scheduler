# HBS ExEd Agentic AI Scheduler

An agentic scheduling coordinator built for **Harvard Business School Executive Education** - autonomously manages multi-party faculty outreach, reply interpretation, and counter-proposal negotiation via Claude, Gmail API, and Streamlit.

---

## Problem Statement

Coordinating faculty schedules for executive education programs at institutions like Harvard Business School is a labor-intensive, high-friction process. Program coordinators must manually reach out to multiple faculty members, track responses, handle scheduling conflicts and counter-proposals, and loop back with updated options - all while managing tight program timelines.

This process is:
- **Time-consuming** - each coordination round requires manual email drafting, sending, and reply tracking
- **Error-prone** - stale replies, missed confirmations, and out-of-sync schedules are common
- **Non-scalable** - coordinators managing multiple programs simultaneously face compounding overhead

This system was built to automate that entire loop - from constraint intake through confirmation - with a human coordinator remaining in control only at key decision points.

---

## What It Does

The system acts as an autonomous scheduling agent that:

1. **Extracts scheduling constraints** from plain-language coordinator input using Claude
2. **Generates concrete schedule options** satisfying all constraints
3. **Drafts and sends outreach emails** to faculty via Gmail, respecting contact hierarchies (direct vs. via assistant)
4. **Polls Gmail for replies** and classifies them - confirmed, counter-proposed, declined, or no response
5. **Handles counter-proposals** by merging new constraints, regenerating schedules, and re-contacting affected parties
6. **Locks the schedule** once all parties confirm, transitioning the request to CONFIRMED state

The coordinator only intervenes at three points:
- Reviewing and confirming outreach emails before they are sent
- Deciding how to handle a counter-proposal (accept, reject, or escalate)
- Answering clarifying questions if the initial input is ambiguous

---

## Architecture

The system is built as a LangChain pipeline with five core modules:

```
Coordinator Input
      │
      ▼
┌─────────────┐
│   Parser    │  Claude extracts structured constraints from natural language
└──────┬──────┘
       │ constraints.json
       ▼
┌─────────────┐
│  Scheduler  │  Claude generates concrete schedule options + contact hierarchy
└──────┬──────┘
       │ schedule_options.json
       ▼
┌─────────────┐
│  Outreach   │  Claude drafts emails → Gmail API sends them
└──────┬──────┘
       │ emails_options.json
       ▼
┌──────────────────┐
│ Reply Interpreter│  Gmail polling → Claude classifies replies
└──────┬───────────┘
       │ replies.json
       ▼
┌─────────────┐
│ Coordinator │  State machine drives transitions + triggers re-outreach
└─────────────┘
```

### State Machine

Every scheduling request moves through a defined state machine:

```
DRAFT → PROPOSED → COUNTER_PROPOSED → CONFIRMED
                        │
                        └──→ ESCALATED
```

- **DRAFT** - request created, not yet sent
- **PROPOSED** - outreach emails sent, awaiting replies
- **COUNTER_PROPOSED** - at least one party proposed a schedule change
- **CONFIRMED** - all parties confirmed, schedule locked
- **ESCALATED** - manual coordinator intervention required (declined, timeout, or manual escalation)

### Key Design Decisions

**Decision-support, not decision-maker** - the system never sends emails or accepts/rejects counter-proposals without coordinator approval. It surfaces options and waits.

**Co-location awareness** - parties sharing a joint session are tracked in colocation groups. If one counter-proposes after others have confirmed, all affected parties are reset to PENDING and re-contacted with updated options.

**Reply threading** - outreach emails are sent via Gmail API and their `Message-ID` headers are stored. Incoming replies are matched via `In-Reply-To` headers, ensuring only genuine replies to system-sent emails are processed.

**Stale reply filtering** - the coordinator only processes replies received after the most recent outreach email was sent to that party, preventing old replies from previous rounds from bleeding into new ones.

**Counter-proposer reset** - when a counter-proposal is accepted, both the colocation group members AND the counter-proposer themselves are reset to PENDING. Everyone must re-confirm the new schedule.

A full implementation-agnostic architecture document is provided in the repository.

---

## Constraint Satisfaction Design

The scheduling pipeline is built around a lightweight constraint satisfaction approach. Rather than using a formal CSP solver, the system represents all scheduling requirements as structured natural language clauses that Claude reasons over directly.

### Constraint Representation

Every scheduling request is parsed into a clause set of the form:

```
"Prof. Eisenmann MUST teach Entrepreneurship Strategy on Monday April 28th at 12:30 for 90 min in Aldrich 112"
"Prof. Eisenmann AND Prof. Kerr MUST attend joint faculty briefing at 09:00 in Aldrich 112"
"NO session CANNOT start before 09:00"
```

Clauses use a strict vocabulary: MUST, CANNOT, AND, OR, NOT. Every generated schedule must satisfy all clauses simultaneously. This makes the constraint set machine-readable for the scheduler and human-readable for the coordinator.

### Constraint Blocks

In addition to clauses, constraints are grouped into typed blocks for downstream agents:

| Block | Purpose |
|---|---|
| `who` | Which faculty are responsible for which sessions |
| `when` | Time windows, dates, durations |
| `where` | Room requirements |
| `contacts` | Contact hierarchy (direct vs. via assistant) |
| `counter_propose` | Which parties may propose alternatives |
| `colocation` | Which parties must share a room and time slot |

Each downstream agent (scheduler, outreach, reply interpreter) reads only the blocks relevant to its task, keeping the pipeline modular.

### Smart Inference

The parser applies inference rules before surfacing ambiguities to the coordinator:

- Joint sessions ("joint briefing", "faculty panel") automatically resolve co-location without asking
- Explicit counter-proposal grants ("both allowed to counter-propose") automatically resolve that block
- Contact routing ("via assistant Kate at kate@hbs.edu") is inferred directly from phrasing

Only genuinely unresolvable gaps (missing session duration, ambiguous contact details) are surfaced as blocking ambiguities.

### Constraint Merging on Counter-Proposals

When a faculty member counter-proposes, the reply interpreter extracts their proposed constraints as override clauses:

```
"Meeting MUST be on Tuesday April 29th at 10:00 for 90 minutes in Aldrich 112"
```

These are merged into the existing constraint set by replacing conflicting time and date clauses while preserving all non-temporal constraints (room assignments, colocation groups, contact routing, topic requirements). The merged constraint set is then passed back to the scheduler to regenerate options, ensuring the new schedule satisfies both the original requirements and the counter-proposer's constraints.

This merge-and-regenerate loop can run multiple times within a single request, with each round producing a fully constraint-satisfying schedule.

---

## Tech Stack

| Layer | Technology |
|---|---|
| LLM | Claude Sonnet (via `langchain-anthropic`) |
| Email | Gmail API (OAuth2, `google-api-python-client`) |
| UI | Streamlit |
| Orchestration | LangChain |
| State persistence | JSON files |
| Language | Python 3.11+ |

---

## Project Structure

```
├── app.py                  # Streamlit UI - Intake and Live Coordination views
├── parser.py               # Constraint extraction from natural language
├── scheduler.py            # Schedule generation + contact hierarchy extraction
├── outreach.py             # Email generation and Gmail sending
├── reply_interpreter.py    # Gmail polling and reply classification
├── coordinator.py          # Coordination loop and state transitions
├── state.py                # State machine (DRAFT → CONFIRMED)
├── main.py                 # CLI runner
├── .streamlit/
│   └── config.toml         # Streamlit theme config
├── .env.example            # Environment variable template
├── .gitignore
└── requirements.txt
```

Runtime JSON files (auto-generated, gitignored):
```
constraints.json            # Extracted scheduling constraints
schedule_options.json       # Generated schedule options + hierarchy
emails_options.json         # Sent email records with Gmail message IDs
replies.json                # Classified reply records
state.json                  # Request state history
processed_replies.json      # Processed reply IDs (deduplication)
```

---

## Setup

### Prerequisites

- Python 3.11+
- An Anthropic API key
- A Google Cloud project with Gmail API enabled

### 1. Clone and install

```bash
git clone https://github.com/AhmedEzazHamidLabib/hbs-exed-agentic-ai-scheduler.git
cd hbs-exed-agentic-ai-scheduler
python -m venv .venv

# Windows
.venv\Scripts\pip install -r requirements.txt

# Mac/Linux
.venv/bin/pip install -r requirements.txt
```

### 2. Environment variables

Copy `.env.example` to `.env` and fill in your key:

```
ANTHROPIC_API_KEY=your_anthropic_api_key_here
```

### 3. Gmail API setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project and enable the **Gmail API**
3. Create OAuth 2.0 credentials (Desktop app)
4. Download `credentials.json` and place it in the project root
5. On first run, a browser window will open for Google sign-in - authenticate and the system will save `token.json` automatically

Required Gmail scopes:
- `https://www.googleapis.com/auth/gmail.send`
- `https://www.googleapis.com/auth/gmail.readonly`

### 4. Run

```bash
streamlit run app.py
```

---

## How to Use

### Intake

1. Open the app and type your scheduling requirements in plain English. Example:

```
Schedule Prof. Thomas Eisenmann (eisenmann@hbs.edu) and Prof. William Kerr
(kerr@hbs.edu) for a joint faculty briefing in Aldrich 112 on Monday April
28th at 09:00 for 2 hours. After the briefing, Prof. Eisenmann will deliver
a 90-minute Entrepreneurship Strategy session at 12:30 in Aldrich 112, and
Prof. Kerr will deliver a 90-minute Innovation & Global Economy session at
14:00 in Aldrich 112. Both professors are allowed to counter-propose.
```

2. The AI extracts constraints and asks clarifying questions if anything is ambiguous (e.g. missing session duration, unspecified counter-proposal permissions).

3. Once constraints are confirmed, the system automatically generates a schedule and drafts outreach emails.

4. Review the email previews and hit **Confirm - Send All Faculty Emails** to send.

### Live Coordination

After sending, the system switches to the Live Coordination view where you can:

- Monitor faculty confirmation status in real time
- See the reply log as responses come in (auto-polls Gmail every 2 minutes)
- Hit **Check for Replies Now** for an immediate poll
- Act on counter-proposals - Accept (regenerates schedule), Reject (re-sends original), or Escalate

### Counter-Proposals

When a faculty member proposes a different time:
- The system surfaces the proposal with a summary
- You choose Accept, Reject, or Escalate
- On Accept - updated constraints are merged, a new schedule is generated, and all affected faculty (including the counter-proposer) are re-contacted automatically
- On Reject - the original schedule is re-sent to that faculty member

### Starting Fresh

Hit **New Request** in the sidebar to clear all state and start a new scheduling request.

---

## Limitations

- Gmail OAuth tokens expire periodically - delete `token.json` and re-authenticate if you see token errors
- The system relies on `In-Reply-To` email headers for reply matching - forwarded replies or replies from a different email client may not be matched
- Counter-proposal constraint merging is LLM-based and may occasionally mis-parse highly ambiguous natural language proposals
- All state is stored in local JSON files - not suitable for multi-user or production deployment without a proper database backend

---

## Author

**Ahmed Ezaz Hamid Labib**
Agentic AI Product Owner - [Tiferet Labs](https://github.com/AhmedEzazHamidLabib)
Michigan State University, Computer Science - Class of 2026
