import streamlit as st
import json
import os
import time
from datetime import datetime

st.set_page_config(
    page_title="HBS Executive Education — Scheduling Coordinator",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@300;400;500;600&display=swap');

    html, body, [class*="css"] { font-family: 'IBM Plex Sans', sans-serif; }
    .stApp { background-color: #ffffff; color: #1a1a1a; }
    div[data-testid="stSidebar"] { background-color: #f5f5f5; border-right: 1px solid #ddd; }

    .hbs-header {
        background: linear-gradient(135deg, #A41034 0%, #7a0c26 100%);
        padding: 18px 24px; margin: -1rem -1rem 24px -1rem;
        border-bottom: 2px solid #7a0c26;
    }
    .hbs-header-title { font-family:'IBM Plex Sans',sans-serif; font-size:13px; font-weight:600; color:#ffffff; letter-spacing:0.08em; text-transform:uppercase; margin:0; }
    .hbs-header-sub { font-family:'IBM Plex Mono',monospace; font-size:10px; color:rgba(255,255,255,0.65); letter-spacing:0.12em; text-transform:uppercase; margin-top:4px; }

    .pipeline-step { background:#f9f9f9; border:1px solid #ddd; border-radius:4px; padding:12px 16px; margin-bottom:8px; }
    .pipeline-step-active { border-color:#A41034; background:#fff0f3; }
    .pipeline-step-done { border-color:#2a7a2a; background:#f0fff4; }
    .pipeline-label { font-family:'IBM Plex Mono',monospace; font-size:10px; letter-spacing:0.1em; text-transform:uppercase; color:#aaa; margin-bottom:4px; }
    .pipeline-label-active { color:#A41034; }
    .pipeline-label-done { color:#2a7a2a; }

    .status-badge { display:inline-block; padding:2px 10px; border-radius:2px; font-family:'IBM Plex Mono',monospace; font-size:10px; letter-spacing:0.1em; font-weight:500; text-transform:uppercase; }
    .status-draft     { background:#e8eef7; color:#2a4a8a; border:1px solid #b0c4de; }
    .status-proposed  { background:#e8f7e8; color:#1a6a1a; border:1px solid #a0d0a0; }
    .status-counter   { background:#fff0f0; color:#A41034; border:1px solid #f0a0a0; }
    .status-escalated { background:#fff8e8; color:#7a5a00; border:1px solid #d0c080; }
    .status-confirmed { background:#e8f7f7; color:#1a6a6a; border:1px solid #a0d0d0; }

    .party-card { background:#f9f9f9; border:1px solid #e0e0e0; border-radius:4px; padding:14px 16px; margin-bottom:10px; }
    .party-name { font-family:'IBM Plex Mono',monospace; font-size:13px; font-weight:500; color:#1a1a1a; }
    .party-meta { font-size:11px; color:#777; margin-top:4px; font-family:'IBM Plex Mono',monospace; }

    .email-preview {
        background:#f9f9f9; border:1px solid #e0e0e0; border-left:3px solid #A41034;
        border-radius:0 4px 4px 0; padding:16px; margin-bottom:12px;
        font-family:'IBM Plex Mono',monospace; font-size:12px; line-height:1.7; color:#333; white-space:pre-wrap;
    }
    .email-header { font-size:11px; color:#888; margin-bottom:10px; padding-bottom:8px; border-bottom:1px solid #e0e0e0; }

    .section-label { font-family:'IBM Plex Mono',monospace; font-size:10px; letter-spacing:0.12em; text-transform:uppercase; color:#999; margin-bottom:12px; }

    .alert-box { background:#fff5f5; border:1px solid #f0c0c0; border-left:3px solid #A41034; border-radius:0 4px 4px 0; padding:14px 16px; margin-bottom:16px; }
    .alert-title { font-family:'IBM Plex Mono',monospace; font-size:11px; color:#A41034; letter-spacing:0.1em; text-transform:uppercase; margin-bottom:8px; }
    .success-box { background:#f0fff4; border:1px solid #a0d0a0; border-left:3px solid #2a7a2a; border-radius:0 4px 4px 0; padding:14px 16px; margin-bottom:16px; }
    .info-box { background:#f0f4ff; border:1px solid #b0c4de; border-left:3px solid #6c8ebf; border-radius:0 4px 4px 0; padding:14px 16px; margin-bottom:16px; }

    .chat-bubble-user { background:#fff0f3; border:1px solid #f0c0c8; border-radius:4px; padding:10px 14px; margin-bottom:8px; font-size:13px; color:#A41034; }
    .chat-bubble-coordinator { background:#f9f9f9; border:1px solid #e0e0e0; border-radius:4px; padding:10px 14px; margin-bottom:8px; font-size:13px; color:#1a1a1a; }

    .stTextArea textarea { background-color:#f9f9f9 !important; border:1px solid #ddd !important; color:#1a1a1a !important; font-family:'IBM Plex Mono',monospace !important; font-size:13px !important; }
    .stButton > button { font-family:'IBM Plex Mono',monospace !important; font-size:11px !important; letter-spacing:0.08em !important; text-transform:uppercase !important; border-radius:2px !important; color:#1a1a1a !important; background-color:#f0f0f0 !important; border:1px solid #ccc !important; padding:8px 16px !important; width:100%; }
    .stButton > button:hover { background-color:#fff0f3 !important; border-color:#A41034 !important; color:#A41034 !important; }
    .stButton > button:active { background-color:#ffe0e5 !important; color:#A41034 !important; }
    .stButton > button[kind="primary"] { background-color:#A41034 !important; border-color:#7a0c26 !important; color:#ffffff !important; }
    .stButton > button[kind="primary"]:hover { background-color:#7a0c26 !important; color:#ffffff !important; }

    .metric-card { background:#f9f9f9; border:1px solid #e0e0e0; border-radius:4px; padding:16px; text-align:center; }
    .metric-value { font-family:'IBM Plex Mono',monospace; font-size:28px; font-weight:500; color:#1a1a1a; }
    .metric-label { font-size:10px; color:#999; text-transform:uppercase; letter-spacing:0.1em; margin-top:4px; }

    .sidebar-logo { font-family:'IBM Plex Sans',sans-serif; font-size:14px; font-weight:600; color:#A41034; letter-spacing:0.05em; margin-bottom:4px; }
    .sidebar-sub { font-family:'IBM Plex Mono',monospace; font-size:9px; color:#999; letter-spacing:0.1em; text-transform:uppercase; margin-bottom:16px; }

    .stCheckbox label, .stToggle label { color:#555 !important; font-family:'IBM Plex Mono',monospace !important; font-size:11px !important; }
    table { font-family:'IBM Plex Mono',monospace !important; font-size:12px !important; color:#333 !important; }
    th { color:#777 !important; font-weight:400 !important; border-bottom:1px solid #ddd !important; }
    td { border-bottom:1px solid #eee !important; }
</style>
""", unsafe_allow_html=True)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONSTRAINTS_FILE = os.path.join(BASE_DIR, "constraints.json")
SCHEDULE_FILE = os.path.join(BASE_DIR, "schedule_options.json")
EMAILS_FILE = os.path.join(BASE_DIR, "emails_options.json")
REPLIES_FILE = os.path.join(BASE_DIR, "replies.json")
STATE_FILE = os.path.join(BASE_DIR, "state.json")
PROCESSED_FILE = os.path.join(BASE_DIR, "processed_replies.json")

DEMO_REQUEST = "Schedule Prof. Thomas Eisenmann (labibahm@msu.edu) and Prof. William Kerr (labibahm7@gmail.com) for a joint faculty briefing in Aldrich 112 on Monday April 28th at 09:00 for 2 hours. After the briefing, Prof. Eisenmann will deliver a 90-minute Entrepreneurship Strategy session at 12:30 in Aldrich 112, and Prof. Kerr will deliver a 90-minute Innovation & Global Economy session at 14:00 in Aldrich 112. Both professors are allowed to counter-propose."

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_json(path):
    if os.path.exists(path):
        with open(path) as f:
            try:
                return json.load(f)
            except:
                return None
    return None

def get_latest_schedule():
    data = load_json(SCHEDULE_FILE)
    if not data:
        return None
    return data[-1] if isinstance(data, list) else data

def get_current_request_state(request_id):
    data = load_json(STATE_FILE)
    if not data:
        return None
    for r in data:
        if r.get("request_id") == request_id:
            return r
    return None

def get_sent_emails(request_id=None):
    data = load_json(EMAILS_FILE) or []
    if request_id:
        return [e for e in data if e.get("request_id") == request_id]
    return data

def get_replies(request_id=None):
    data = load_json(REPLIES_FILE) or []
    if request_id:
        return [r for r in data if r.get("request_id") == request_id]
    return data

def status_badge(status):
    cls = {
        "DRAFT": "status-draft", "PROPOSED": "status-proposed",
        "COUNTER_PROPOSED": "status-counter", "ESCALATED": "status-escalated",
        "CONFIRMED": "status-confirmed",
    }.get(status, "status-draft")
    return f'<span class="status-badge {cls}">{status}</span>'

def party_status_badge(status):
    colors = {"PENDING": "#2a4a8a", "WAITING": "#999", "CONFIRMED": "#1a6a6a"}
    color = colors.get(status, "#999")
    return f'<span style="font-family:\'IBM Plex Mono\',monospace;font-size:10px;color:{color};border:1px solid {color}44;padding:1px 8px;border-radius:2px;">{status}</span>'

def poll_and_process(rid):
    try:
        from reply_interpreter import run_interpreter
        from coordinator import run_coordinator
        new_replies = run_interpreter(request_id=rid)
        if new_replies:
            run_coordinator(request_id=rid)
        return len(new_replies)
    except Exception as e:
        st.error(f"Poll error: {e}")
        return 0

def clear_all_state():
    """Delete all JSON state files and reset session state."""
    for f in [CONSTRAINTS_FILE, SCHEDULE_FILE, EMAILS_FILE, REPLIES_FILE, STATE_FILE, PROCESSED_FILE]:
        if os.path.exists(f):
            os.remove(f)
    st.session_state.view = "intake"
    st.session_state.chat_history = []
    st.session_state.constraints = None
    st.session_state.parser_history = []
    st.session_state.schedule = None
    st.session_state.generated_emails = []
    st.session_state.intake_stage = "input"

def generate_emails_for_schedule(schedule):
    from outreach import chain as outreach_chain, get_party_sessions, load_emails, get_previous_status
    rid = schedule["request_id"]
    hierarchy = schedule.get("hierarchy", [])
    options = schedule.get("options", [])
    pending = [p for p in hierarchy if p.get("status") == "PENDING"]
    generated = []
    for party in pending:
        previous_sent_at = get_previous_status(party["party"], rid)
        is_recontact = previous_sent_at is not None
        if previous_sent_at:
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
        party_sessions = get_party_sessions(party, options)
        if not party_sessions:
            party_sessions = options
        result = outreach_chain.invoke({
            "summary": schedule["summary"],
            "party": json.dumps(party, indent=2),
            "sessions": json.dumps(party_sessions, indent=2),
            "is_recontact": str(is_recontact),
            "recontact_reason": reason,
        })
        if result["email"]:
            generated.append({
                "party": party,
                "email": result["email"],
                "is_recontact": is_recontact,
                "recontact_reason": reason,
            })
    return generated

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
for key, default in {
    "view": "intake",
    "chat_history": [],
    "constraints": None,
    "parser_history": [],
    "schedule": None,
    "generated_emails": [],
    "intake_stage": "input",
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown('<div class="sidebar-logo">Harvard Business School</div>', unsafe_allow_html=True)
    st.markdown('<div class="sidebar-sub">Executive Education · AI Scheduling Coordinator</div>', unsafe_allow_html=True)
    st.markdown('<hr style="border-color:#ddd;margin:0 0 12px 0;">', unsafe_allow_html=True)

    # New Request button
    if st.button("⟳ New Request", key="btn_new_request", use_container_width=True):
        clear_all_state()
        st.rerun()

    st.markdown('<hr style="border-color:#ddd;margin:12px 0;">', unsafe_allow_html=True)

    # Active request info
    schedule = get_latest_schedule()
    if schedule:
        rid = schedule.get("request_id", "—")
        state = get_current_request_state(rid)
        status = state["status"] if state else "DRAFT"
        hierarchy = schedule.get("hierarchy", [])
        confirmed = sum(1 for p in hierarchy if p.get("status") == "CONFIRMED")

        st.markdown(f'<div style="font-family:\'IBM Plex Mono\',monospace;font-size:10px;color:#999;margin-bottom:4px;">ACTIVE REQUEST</div>', unsafe_allow_html=True)
        st.markdown(f'`{rid}`')
        st.markdown(status_badge(status), unsafe_allow_html=True)
        st.markdown("")
        st.markdown(f'<div class="metric-card"><div class="metric-value">{confirmed}/{len(hierarchy)}</div><div class="metric-label">Faculty Confirmed</div></div>', unsafe_allow_html=True)
        st.markdown("")

    # Pipeline steps
    st.markdown('<div class="section-label">Pipeline</div>', unsafe_allow_html=True)
    intake_stage = st.session_state.intake_stage
    steps = [
        ("1", "Constraint Intake", intake_stage in ("schedule_ready", "emails_ready") or st.session_state.view == "live", intake_stage == "input" and st.session_state.view == "intake"),
        ("2", "Schedule Generation", intake_stage in ("schedule_ready", "emails_ready") or st.session_state.view == "live", intake_stage == "schedule_ready"),
        ("3", "Faculty Outreach", intake_stage == "emails_ready" or st.session_state.view == "live", intake_stage == "emails_ready"),
        ("4", "Live Coordination", st.session_state.view == "live", st.session_state.view == "live"),
    ]
    for num, label, done, active in steps:
        cls = "pipeline-step-done" if done and not active else ("pipeline-step-active" if active else "pipeline-step")
        label_cls = "pipeline-label-done" if done and not active else ("pipeline-label-active" if active else "pipeline-label")
        icon = "✓" if done and not active else num
        st.markdown(f'<div class="pipeline-step {cls}"><div class="{label_cls}">{icon} — {label}</div></div>', unsafe_allow_html=True)

    st.markdown("")
    col_a, col_b = st.sidebar.columns(2)
    with col_a:
        if st.button("← Intake", key="nav_intake", use_container_width=True):
            st.session_state.view = "intake"
            st.rerun()
    with col_b:
        if st.button("Live →", key="nav_live", use_container_width=True):
            st.session_state.view = "live"
            st.rerun()

    st.markdown('<hr style="border-color:#ddd;margin:16px 0 12px 0;">', unsafe_allow_html=True)
    st.markdown('<div style="font-family:\'IBM Plex Mono\',monospace;font-size:9px;color:#bbb;text-align:center;">AI Scheduling Coordinator · HBS ExEd</div>', unsafe_allow_html=True)

# ===========================================================================
# VIEW: INTAKE
# ===========================================================================
if st.session_state.view == "intake":
    st.markdown('<div class="hbs-header"><div class="hbs-header-title">Harvard Business School — Executive Education</div><div class="hbs-header-sub">Scheduling Coordinator · Intake & Outreach</div></div>', unsafe_allow_html=True)

    left, right = st.columns([3, 2])

    with left:
        st.markdown('<div class="section-label">① Constraint Intake</div>', unsafe_allow_html=True)

        for msg in st.session_state.chat_history:
            cls = "chat-bubble-user" if msg["role"] == "user" else "chat-bubble-coordinator"
            label = "Coordinator" if msg["role"] == "user" else "AI System"
            st.markdown(f'<div class="{cls}"><strong>{label}</strong> — {msg["content"]}</div>', unsafe_allow_html=True)

        if st.session_state.intake_stage == "input":
            user_input = st.text_area(
                "Program scheduling requirements",
                placeholder=DEMO_REQUEST,
                height=120,
                key="constraint_input",
            )
            if st.button("Submit Requirements", use_container_width=True, key="btn_send"):
                if user_input.strip():
                    with st.spinner("Extracting scheduling constraints..."):
                        try:
                            from langchain_core.messages import HumanMessage, AIMessage
                            from parser import chain as parser_chain

                            st.session_state.chat_history.append({"role": "user", "content": user_input.strip()})
                            result = parser_chain.invoke({
                                "history": st.session_state.parser_history,
                                "user_input": user_input.strip(),
                            })
                            reply = result["reply"]
                            constraints = result["constraints"]
                            raw = result["raw"]

                            st.session_state.parser_history.append(HumanMessage(content=user_input.strip()))
                            st.session_state.parser_history.append(AIMessage(content=raw))

                            if constraints:
                                st.session_state.constraints = constraints
                            st.session_state.chat_history.append({"role": "coordinator", "content": reply})

                            if constraints and constraints.get("ready"):
                                with open(CONSTRAINTS_FILE, "w") as f:
                                    json.dump(constraints, f, indent=2)
                                from scheduler import run_scheduler_langchain
                                sched = run_scheduler_langchain(CONSTRAINTS_FILE)
                                if sched:
                                    st.session_state.schedule = sched
                                    st.session_state.intake_stage = "schedule_ready"
                                    generated = generate_emails_for_schedule(sched)
                                    st.session_state.generated_emails = generated
                                    if generated:
                                        st.session_state.intake_stage = "emails_ready"
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error: {e}")

        elif st.session_state.intake_stage in ("schedule_ready", "emails_ready"):
            c = st.session_state.constraints
            if c and not c.get("ready"):
                user_input = st.text_area("Your response", height=80, key="followup_input")
                if st.button("Submit", use_container_width=True, key="btn_followup"):
                    if user_input.strip():
                        with st.spinner("Processing..."):
                            try:
                                from langchain_core.messages import HumanMessage, AIMessage
                                from parser import chain as parser_chain

                                st.session_state.chat_history.append({"role": "user", "content": user_input.strip()})
                                result = parser_chain.invoke({
                                    "history": st.session_state.parser_history,
                                    "user_input": user_input.strip(),
                                })
                                constraints = result["constraints"]
                                raw = result["raw"]
                                st.session_state.parser_history.append(HumanMessage(content=user_input.strip()))
                                st.session_state.parser_history.append(AIMessage(content=raw))
                                if constraints:
                                    st.session_state.constraints = constraints
                                st.session_state.chat_history.append({"role": "coordinator", "content": result["reply"]})
                                if constraints and constraints.get("ready"):
                                    with open(CONSTRAINTS_FILE, "w") as f:
                                        json.dump(constraints, f, indent=2)
                                    from scheduler import run_scheduler_langchain
                                    sched = run_scheduler_langchain(CONSTRAINTS_FILE)
                                    if sched:
                                        st.session_state.schedule = sched
                                        generated = generate_emails_for_schedule(sched)
                                        st.session_state.generated_emails = generated
                                        st.session_state.intake_stage = "emails_ready" if generated else "schedule_ready"
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error: {e}")
            else:
                st.markdown('<div class="success-box"><div class="alert-title">✓ Constraints locked — schedule generated automatically</div></div>', unsafe_allow_html=True)

        # Stage 2: Schedule
        if st.session_state.intake_stage in ("schedule_ready", "emails_ready"):
            st.markdown("---")
            st.markdown('<div class="section-label">② Generated Schedule Options</div>', unsafe_allow_html=True)
            sched = st.session_state.schedule or get_latest_schedule()
            if sched:
                for opt in sched.get("options", []):
                    with st.expander(f"Option {opt['option']}", expanded=True):
                        for session in opt.get("sessions", []):
                            st.markdown(f"""
| | |
|---|---|
| **Session** | {session.get('topic', '—')} |
| **Faculty** | {session.get('instructor', '—')} |
| **Date** | {session.get('day', '—')} |
| **Time** | {session.get('start', '—')} — {session.get('end', '—')} ({session.get('duration_min', '—')} min) |
| **Room** | {session.get('room', '—')} |
""")

        # Stage 3: Email Preview
        if st.session_state.intake_stage == "emails_ready":
            st.markdown("---")
            st.markdown('<div class="section-label">③ Faculty Outreach Preview</div>', unsafe_allow_html=True)

            if not st.session_state.generated_emails:
                if st.button("Regenerate Emails", key="btn_regen"):
                    with st.spinner("Regenerating emails..."):
                        sched = st.session_state.schedule or get_latest_schedule()
                        if sched:
                            generated = generate_emails_for_schedule(sched)
                            st.session_state.generated_emails = generated
                            st.rerun()
            else:
                for i, item in enumerate(st.session_state.generated_emails, 1):
                    party = item["party"]
                    email = item["email"]
                    is_recontact = item["is_recontact"]
                    can_cp = party.get("can_counter_propose", False)
                    tag = "RE-CONTACT" if is_recontact else "INITIAL OUTREACH"
                    tag_color = "#c0392b" if is_recontact else "#2a4a8a"

                    st.markdown(f"""
<div class="email-preview">
<div class="email-header">
EMAIL {i} &nbsp;·&nbsp; <span style="color:{tag_color}">{tag}</span> &nbsp;·&nbsp;
TO: {email.get('to')} &nbsp;·&nbsp;
CAN COUNTER: {'YES' if can_cp else 'NO'} &nbsp;·&nbsp;
COLOC: {party.get('colocation_group') or 'none'}
<br>SUBJECT: {email.get('subject')}
</div>{email.get('body', '')}
</div>
""", unsafe_allow_html=True)

                st.markdown("---")
                confirm_col, regen_col = st.columns([2, 1])
                with confirm_col:
                    if st.button("✓ CONFIRM — Send All Faculty Emails", type="primary", key="btn_confirm_send"):
                        with st.spinner("Sending via Gmail..."):
                            try:
                                from outreach import get_gmail_service, send_via_gmail, load_emails, save_emails
                                from state import Status, get_request, create_request, transition

                                sched = st.session_state.schedule or get_latest_schedule()
                                rid = sched["request_id"]
                                service = get_gmail_service()
                                sent_emails = []

                                for item in st.session_state.generated_emails:
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

                                state_rec = get_request(rid)
                                if not state_rec:
                                    create_request(rid, sched["summary"])
                                    state_rec = get_request(rid)
                                if state_rec and state_rec["status"] == "DRAFT":
                                    transition(rid, Status.PROPOSED, note="Faculty outreach sent via UI")

                                sent_count = sum(1 for e in sent_emails if e["sent"])
                                st.success(f"✓ {sent_count}/{len(sent_emails)} faculty emails sent.")
                                st.session_state.generated_emails = []
                                st.session_state.view = "live"
                                st.rerun()
                            except Exception as e:
                                st.error(f"Send error: {e}")
                with regen_col:
                    if st.button("↺ Regenerate Emails", key="btn_regen2"):
                        with st.spinner("Regenerating..."):
                            sched = st.session_state.schedule or get_latest_schedule()
                            if sched:
                                generated = generate_emails_for_schedule(sched)
                                st.session_state.generated_emails = generated
                                st.rerun()

    with right:
        st.markdown('<div class="section-label">Extracted Constraints</div>', unsafe_allow_html=True)
        c = st.session_state.constraints
        if c:
            if c.get("ready"):
                st.markdown('<div class="success-box"><div class="alert-title">✓ Ready for scheduling</div></div>', unsafe_allow_html=True)
            else:
                st.markdown('<div class="alert-box"><div class="alert-title">⚠ Awaiting clarification</div></div>', unsafe_allow_html=True)

            if c.get("clauses"):
                st.markdown('<div class="section-label">Clauses</div>', unsafe_allow_html=True)
                for clause in c["clauses"]:
                    st.markdown(f'`{clause}`')

            if c.get("blocks"):
                for key, items in c["blocks"].items():
                    st.markdown(f'<div class="section-label">{key}</div>', unsafe_allow_html=True)
                    for item in items:
                        st.markdown(f"— {item}")

            if c.get("ambiguities"):
                st.markdown('<div class="section-label">Requires Clarification</div>', unsafe_allow_html=True)
                for a in c["ambiguities"]:
                    st.warning(a)
        else:
            st.markdown('<div style="color:#999;font-family:\'IBM Plex Mono\',monospace;font-size:12px;">Submit program requirements to begin.</div>', unsafe_allow_html=True)

        sched = st.session_state.schedule or get_latest_schedule()
        if sched and st.session_state.intake_stage in ("schedule_ready", "emails_ready"):
            st.markdown("---")
            st.markdown('<div class="section-label">Faculty & Contact Hierarchy</div>', unsafe_allow_html=True)
            for party in sched.get("hierarchy", []):
                can_cp = party.get("can_counter_propose", False)
                coloc = party.get("colocation_group")
                st.markdown(f"""
<div class="party-card">
    <div class="party-name">{party['party']}</div>
    <div class="party-meta">
        {party.get('contact_email', '—')}<br>
        via {party.get('contact_via', '—')} · coloc: {coloc or 'none'}<br>
        counter-propose: {'yes' if can_cp else 'no'}
    </div>
    <div style="margin-top:8px;">{party_status_badge(party.get('status', 'PENDING'))}</div>
</div>
""", unsafe_allow_html=True)

# ===========================================================================
# VIEW: LIVE
# ===========================================================================
elif st.session_state.view == "live":
    st.markdown('<div class="hbs-header"><div class="hbs-header-title">Harvard Business School — Executive Education</div><div class="hbs-header-sub">Scheduling Coordinator · Live Coordination Status</div></div>', unsafe_allow_html=True)

    schedule = get_latest_schedule()
    if not schedule:
        st.info("No active scheduling request. Return to Intake to begin.")
    else:
        rid = schedule["request_id"]
        state = get_current_request_state(rid)
        status = state["status"] if state else "DRAFT"
        hierarchy = schedule.get("hierarchy", [])
        confirmed = sum(1 for p in hierarchy if p.get("status") == "CONFIRMED")
        replies = get_replies(rid)
        sent = get_sent_emails(rid)

        ref_col1, ref_col2, ref_col3 = st.columns([1, 1, 2])
        with ref_col1:
            auto_refresh = st.toggle("Auto-poll Gmail", value=True)
        with ref_col2:
            interval_choice = st.selectbox("Interval", [30, 60, 120, 300], index=2, label_visibility="collapsed")
        with ref_col3:
            st.markdown(f'**Status** &nbsp; {status_badge(status)}', unsafe_allow_html=True)

        m1, m2, m3 = st.columns(3)
        with m1:
            st.markdown(f'<div class="metric-card"><div class="metric-value">{confirmed}/{len(hierarchy)}</div><div class="metric-label">Faculty Confirmed</div></div>', unsafe_allow_html=True)
        with m2:
            st.markdown(f'<div class="metric-card"><div class="metric-value">{len(sent)}</div><div class="metric-label">Emails Sent</div></div>', unsafe_allow_html=True)
        with m3:
            st.markdown(f'<div class="metric-card"><div class="metric-value">{len(replies)}</div><div class="metric-label">Replies Received</div></div>', unsafe_allow_html=True)

        st.markdown("")

        # Counter-proposal alert
        if status == "COUNTER_PROPOSED":
            latest_send_time = max((e.get("sent_at", "") for e in sent if e.get("sent")), default="")
            unresolved = [
                r for r in replies
                if r.get("classification") == "COUNTER_PROPOSED"
                and r.get("replied_at", "") > latest_send_time
            ]
            if unresolved:
                latest = unresolved[-1]
                st.markdown(f"""
<div class="alert-box">
    <div class="alert-title">↔ Faculty Counter-Proposal — Coordinator Decision Required</div>
    <b>From:</b> {latest['party']} ({latest['contact_email']})<br>
    <b>Proposal:</b> {latest['summary']}
</div>
""", unsafe_allow_html=True)
                dec_col1, dec_col2, dec_col3 = st.columns(3)
                with dec_col1:
                    if st.button("✓ Accept — Regenerate & Re-send", key="btn_accept", use_container_width=True):
                        with st.spinner("Accepting counter-proposal..."):
                            try:
                                from state import resolve_counter_proposal
                                from coordinator import save_schedule, load_schedule as cs_load, reset_colocation_members, save_constraints
                                from scheduler import run_scheduler_langchain

                                sched = cs_load()
                                colocation_group = latest.get("colocation_group")

                                # Always set recontact_reason — counter-proposer and colocation members all need re-contact
                                recontact_reason = f"{latest['party']} proposed a schedule change. Updated options are being sent to all affected faculty."

                                if colocation_group:
                                    sched, reset_parties = reset_colocation_members(sched, colocation_group, latest["party"])
                                    save_schedule(sched)

                                # Reset the counter-proposer themselves on the same sched object
                                for party in sched["hierarchy"]:
                                    if party["party"] == latest["party"]:
                                        party["status"] = "PENDING"
                                save_schedule(sched)

                                if latest.get("merged_constraints"):
                                    merged = latest["merged_constraints"]
                                    merged.pop("_merge_log", None)
                                    merged["ready"] = True
                                    merged["request_id"] = rid
                                    save_constraints(merged)

                                resolve_counter_proposal(rid, accept=True)
                                new_schedule = run_scheduler_langchain(CONSTRAINTS_FILE)
                                if new_schedule:
                                    st.session_state.schedule = new_schedule
                                    with st.spinner("Generating updated emails..."):
                                        generated = generate_emails_for_schedule(new_schedule)
                                        st.session_state.generated_emails = generated
                                        st.session_state.intake_stage = "emails_ready"
                                    st.session_state.view = "intake"
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error: {e}")
                with dec_col2:
                    if st.button("✗ Reject — Re-send Original", key="btn_reject", use_container_width=True):
                        with st.spinner("Rejecting..."):
                            try:
                                from state import Status, transition
                                from coordinator import save_schedule, load_schedule as cs_load

                                transition(rid, Status.PROPOSED, note="Counter-proposal rejected via UI")
                                sched = cs_load()
                                for party in sched["hierarchy"]:
                                    if party["party"] == latest["party"]:
                                        party["status"] = "PENDING"
                                save_schedule(sched)
                                st.session_state.schedule = sched
                                with st.spinner("Regenerating emails..."):
                                    generated = generate_emails_for_schedule(sched)
                                    st.session_state.generated_emails = generated
                                    st.session_state.intake_stage = "emails_ready"
                                st.session_state.view = "intake"
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error: {e}")
                with dec_col3:
                    if st.button("⚠ Escalate to Coordinator", key="btn_escalate", use_container_width=True):
                        with st.spinner("Escalating..."):
                            try:
                                from state import Status, transition
                                transition(rid, Status.ESCALATED, note=f"Escalated via UI — counter-proposal from {latest['party']}")
                                st.warning("Request escalated. Manual coordinator intervention required.")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error: {e}")

        # Confirmed schedule
        if status == "CONFIRMED":
            st.markdown('<div class="success-box"><div class="alert-title">✓ Schedule Confirmed — All Faculty Approved</div></div>', unsafe_allow_html=True)
            confirmed_option = next((p.get("confirmed_option") for p in hierarchy if p.get("confirmed_option")), None)
            if confirmed_option:
                for opt in schedule.get("options", []):
                    if opt["option"] == confirmed_option:
                        for session in opt.get("sessions", []):
                            st.markdown(f"""
| | |
|---|---|
| **Session** | {session.get('topic')} |
| **Faculty** | {session.get('instructor')} |
| **Date** | {session.get('day')} |
| **Time** | {session.get('start')} — {session.get('end')} |
| **Room** | {session.get('room')} |
""")

        st.markdown("---")

        col_l, col_r = st.columns(2)
        with col_l:
            st.markdown('<div class="section-label">Faculty Confirmation Status</div>', unsafe_allow_html=True)
            for party in hierarchy:
                st.markdown(f"""
<div class="party-card">
    <div class="party-name">{party['party']} &nbsp; {party_status_badge(party.get('status','PENDING'))}</div>
    <div class="party-meta">{party.get('contact_email')} · coloc: {party.get('colocation_group') or 'none'}</div>
</div>
""", unsafe_allow_html=True)

            st.markdown('<div class="section-label" style="margin-top:16px;">Session Schedule</div>', unsafe_allow_html=True)
            for opt in schedule.get("options", []):
                for session in opt.get("sessions", []):
                    st.markdown(f"""
<div class="party-card">
    <div class="party-name">{session.get('topic')}</div>
    <div class="party-meta">{session.get('instructor')}<br>{session.get('day')} · {session.get('start')}–{session.get('end')} · {session.get('room')}</div>
</div>
""", unsafe_allow_html=True)
                break

        with col_r:
            st.markdown('<div class="section-label">Reply Log</div>', unsafe_allow_html=True)
            if replies:
                for r in reversed(replies):
                    cls_color = {
                        "CONFIRMED": "#1a6a6a",
                        "COUNTER_PROPOSED": "#A41034",
                        "DECLINED": "#A41034",
                        "NO_RESPONSE": "#999",
                    }.get(r.get("classification"), "#999")
                    st.markdown(f"""
<div class="party-card">
    <div class="party-name" style="color:{cls_color}">{r.get('classification')}</div>
    <div class="party-meta">{r.get('party')} · {r.get('replied_at','')[:16]}</div>
    <div style="font-size:12px;color:#777;margin-top:6px;">{r.get('summary','')}</div>
</div>
""", unsafe_allow_html=True)
            else:
                st.markdown('<div style="color:#999;font-size:12px;font-family:\'IBM Plex Mono\',monospace;">Awaiting faculty replies.</div>', unsafe_allow_html=True)

            if sent:
                st.markdown('<div class="section-label" style="margin-top:16px;">Outreach Log</div>', unsafe_allow_html=True)
                for e in reversed(sent):
                    tag = "RE-CONTACT" if e.get("is_recontact") else "INITIAL"
                    color = "#c0392b" if e.get("is_recontact") else "#2a4a8a"
                    st.markdown(f"""
<div class="party-card">
    <div class="party-name" style="color:{color}">{tag}</div>
    <div class="party-meta">{e.get('party')} · {e.get('sent_at','')[:16]}<br>{e.get('contact_email')}</div>
</div>
""", unsafe_allow_html=True)

        st.markdown("---")
        check_col, _ = st.columns([1, 3])
        with check_col:
            if st.button("🔄 Check for Replies Now", key="btn_poll", use_container_width=True):
                with st.spinner("Polling Gmail for faculty replies..."):
                    count = poll_and_process(rid)
                    if count > 0:
                        st.success(f"Found {count} new reply(s). Processed.")
                    else:
                        st.info("No new replies found.")
                    st.rerun()

        if state and state.get("history"):
            with st.expander("Request History"):
                for entry in reversed(state["history"]):
                    st.markdown(f'`{entry["timestamp"][:16]}` **{entry["status"]}** — {entry.get("note","")}')

        @st.fragment(run_every=interval_choice)
        def auto_poll_fragment():
            _schedule = get_latest_schedule()
            if not _schedule:
                return
            _rid = _schedule.get("request_id")
            _state = get_current_request_state(_rid)
            _status = _state["status"] if _state else "DRAFT"
            if _status not in ("PROPOSED", "COUNTER_PROPOSED"):
                return
            poll_and_process(_rid)

        if auto_refresh:
            auto_poll_fragment()