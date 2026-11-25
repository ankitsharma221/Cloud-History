"""Streamlit Web UI Dashboard for Cloud Resource Archaeologist.

Interactive UI for exploring cloud resource provenance, ownership, risk verdicts,
and executing reversible decommissioning workflows.
"""

import sys
import os
from pathlib import Path

# Add project root directory to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st
import pandas as pd
from datetime import datetime

from engine.collectors.aws_collector import AWSCollector
from engine.collectors.cloudtrail_collector import CloudTrailCollector
from engine.linker import Linker
from engine.timeline_builder import TimelineBuilder
from engine.owner_resolver import OwnerResolver
from engine.risk_engine import RiskEngine
from engine.readiness_checker import ReadinessChecker
from db.database import SessionLocal, init_db, load_seed_data
from db.models_db import DBResource, DBOwner, DBQuarantine, DBEvent
from engine.models import RiskLevel, ConfidenceLevel

import os
from dotenv import load_dotenv

load_dotenv(".env")

# Initialize database
init_db()
if os.getenv("APP_ENV", "development").lower() != "production":
    load_seed_data()

st.set_page_config(
    page_title="Cloud Resource Archaeologist",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for clean layout
st.markdown("""
<style>
    .block-container { padding-top: 2rem; padding-bottom: 2rem; max-width: 95%; }
    .main-header { font-size: 2.2rem; font-weight: 700; color: #1E3A8A; margin-bottom: 0.2rem; }
    .sub-header { font-size: 1.05rem; color: #4B5563; margin-bottom: 1.2rem; }
    .badge-high { background-color: #FEE2E2; color: #991B1B; padding: 4px 10px; border-radius: 12px; font-weight: 600; font-size: 0.85rem; }
    .badge-med { background-color: #FEF3C7; color: #92400E; padding: 4px 10px; border-radius: 12px; font-weight: 600; font-size: 0.85rem; }
    .badge-low { background-color: #D1FAE5; color: #065F46; padding: 4px 10px; border-radius: 12px; font-weight: 600; font-size: 0.85rem; }
    .badge-blocked { background-color: #F3F4F6; color: #4B5563; padding: 4px 10px; border-radius: 12px; font-weight: 600; font-size: 0.85rem; }
    .timeline-item { border-left: 3px solid #3B82F6; padding-left: 14px; margin-bottom: 16px; }
</style>
""", unsafe_allow_html=True)

# Engines
linker = Linker()
timeline_builder = TimelineBuilder()
owner_resolver = OwnerResolver()
risk_engine = RiskEngine()
# ── Sidebar ──────────────────────────────────────────────────────────────────

st.sidebar.title("🔍 Resource Archaeologist")
st.sidebar.caption("Evidence-in. Safe decisions out.")

# Environment Mode Switcher (Live AWS vs Seed Data)
env_choice = st.sidebar.radio(
    "🌐 Data Source Environment",
    ["AWS Live (ap-south-1 Mumbai)", "Seed Sandbox Data"],
    index=0
)
is_live_aws = ("AWS Live" in env_choice)

aws_collector = AWSCollector(region_name=os.getenv("AWS_REGION", "ap-south-1"), use_seed=not is_live_aws)
cloudtrail_collector = CloudTrailCollector(region_name=os.getenv("AWS_REGION", "ap-south-1"), use_seed=not is_live_aws)

linker = Linker(aws_collector=aws_collector, cloudtrail_collector=cloudtrail_collector)
timeline_builder = TimelineBuilder()
owner_resolver = OwnerResolver()
risk_engine = RiskEngine()
readiness_checker = ReadinessChecker(aws_collector=aws_collector, cloudtrail_collector=cloudtrail_collector)

# Check readiness
readiness = readiness_checker.check_readiness()
st.sidebar.markdown("### 📡 Audit Signals Readiness")
st.sidebar.progress(readiness.coverage_score)
for sig, is_avail in readiness.signals_available.items():
    icon = "✅" if is_avail else "❌"
    st.sidebar.markdown(f"**{icon}** {sig}")

st.sidebar.divider()
st.sidebar.markdown("### ⚙️ Filters")
selected_type = st.sidebar.selectbox("Resource Type", ["All", "ec2_instance", "ebs_volume", "security_group"])
selected_risk = st.sidebar.selectbox("Risk Level", ["All", "LOW_RISK", "MEDIUM_RISK", "HIGH_RISK", "BLOCKED"])

# ── Header & High-Level Metrics ──────────────────────────────────────────────

st.markdown('<div class="main-header">🔍 Cloud Resource Archaeologist</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Know why every cloud resource exists. Attribute owners with confidence. Retire safely with zero fear.</div>', unsafe_allow_html=True)

# Load data
linked_all = linker.link_all()
resources_data = []

total_cost = 0.0
potential_savings = 0.0

st.sidebar.markdown(f"**Active Environment:** `{'Live AWS Mumbai (ap-south-1)' if is_live_aws else 'Seed Sandbox Mode'}`")

for rid, lr in linked_all.items():
    res = lr.resource
    owner = owner_resolver.resolve_owner(lr)
    verdict = risk_engine.evaluate_risk(lr)

    total_cost += res.cost_per_month
    if verdict.risk_level in [RiskLevel.LOW_RISK, RiskLevel.MEDIUM_RISK]:
        potential_savings += verdict.monthly_savings

    resources_data.append({
        "id": res.id,
        "name": res.name or res.id,
        "type": res.resource_type.value,
        "state": res.state.value,
        "cost_per_month": res.cost_per_month,
        "owner": owner.name,
        "owner_confidence": owner.confidence.value,
        "risk_level": verdict.risk_level.value,
        "in_terraform": "Yes" if lr.in_terraform else "No",
        "evidence_coverage": f"{lr.evidence_coverage_ratio:.0%}",
        "linked": lr
    })

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Resources", len(resources_data))
col2.metric("Total Monthly Cloud Bill", f"${total_cost:,.2f} / mo")
col3.metric("Identified Savings", f"${potential_savings:,.2f} / mo")
col4.metric("Audit Coverage Score", f"{readiness.coverage_score:.0%}")

st.divider()

# ── Filter Resources ─────────────────────────────────────────────────────────

filtered = resources_data
if selected_type != "All":
    filtered = [r for r in filtered if r["type"] == selected_type]
if selected_risk != "All":
    filtered = [r for r in filtered if r["risk_level"] == selected_risk]

# ── Resource Explorer ────────────────────────────────────────────────────────

st.subheader("📋 Cloud Inventory & Provenance Overview")

df_display = pd.DataFrame([
    {
        "Resource ID": r["id"],
        "Name": r["name"],
        "Type": r["type"],
        "State": r["state"],
        "Cost / mo": f"${r['cost_per_month']:.2f}",
        "Owner": r["owner"],
        "Confidence": r["owner_confidence"],
        "Risk Verdict": r["risk_level"],
        "Terraform?": r["in_terraform"],
        "Evidence": r["evidence_coverage"]
    }
    for r in filtered
])

st.dataframe(df_display, use_container_width=True)

# ── Deep Investigation Card ──────────────────────────────────────────────────

st.divider()
st.subheader("🕵️ Deep Archaeological Investigation")

resource_options = [f"{r['id']} ({r['name']}) - [{r['risk_level']}]" for r in filtered]
if not resource_options:
    st.info("No resources match the selected filters.")
    st.stop()

selected_choice = st.selectbox("Select a resource to inspect:", resource_options)
selected_id = selected_choice.split()[0]
selected_item = next(r for r in filtered if r["id"] == selected_id)
lr = selected_item["linked"]
res = lr.resource

# Build timeline, owner, verdict
timeline = timeline_builder.build_timeline(lr)
story = timeline_builder.format_story_summary(timeline)
owner = owner_resolver.resolve_owner(lr)
verdict = risk_engine.evaluate_risk(lr)

# Tabs
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📜 1. Why Does It Exist? (Timeline)",
    "👤 2. Who Owns It? (Ownership)",
    "⚖️ 3. Can We Delete It? (Risk Verdict)",
    "🛡️ 4. Safe Reversible Quarantine",
    "🗺️ 5. Architecture & ER Workflow"
])

# ── Tab 1: Timeline ──────────────────────────────────────────────────────────
with tab1:
    st.markdown(f"#### Provenance History for `{res.id}` ({res.name})")

    col_meta1, col_meta2, col_meta3 = st.columns(3)
    with col_meta1:
        st.write(f"**Type:** `{res.resource_type.value}`")
        st.write(f"**Region:** `{res.region}`")
    with col_meta2:
        st.write(f"**Cost:** `${res.cost_per_month:.2f} / month`")
        st.write(f"**Terraform Managed:** `{'Yes' if lr.in_terraform else 'No'}`")
    with col_meta3:
        st.write(f"**Evidence Coverage:** `{lr.evidence_coverage_ratio:.1%} ({len(lr.clues_found)}/6 clues)`")
        st.write(f"**Current State:** `{res.state.value}`")

    st.markdown("##### 🔍 Clue Discovery")
    c_found, c_miss = st.columns(2)
    with c_found:
        st.write("**Discovered Clues:**")
        for c in lr.clues_found:
            st.markdown(f"- ✅ {c}")
    with c_miss:
        st.write("**Missing / Unavailable Clues:**")
        if lr.clues_missing:
            for m in lr.clues_missing:
                st.markdown(f"- ⚠️ {m}")
        else:
            st.markdown("*- None. All core audit clues available.*")

    st.markdown("##### 📅 Chronological Provenance Story")
    if story:
        for s in story:
            st.markdown(f'<div class="timeline-item">{s}</div>', unsafe_allow_html=True)
    else:
        st.info("No CloudTrail or Git audit events found within current log retention window.")

# ── Tab 2: Ownership ─────────────────────────────────────────────────────────
with tab2:
    st.markdown(f"#### Ownership Attribution for `{res.id}`")

    conf_badge_class = "badge-high" if owner.confidence == ConfidenceLevel.HIGH else ("badge-med" if owner.confidence == ConfidenceLevel.MEDIUM else "badge-low")
    st.markdown(f"**Attributed Owner:** ### {owner.name} <span class='{conf_badge_class}'>{owner.confidence.value} CONFIDENCE</span>", unsafe_allow_html=True)
    st.write(f"**Source Step:** `{owner.source.value}`")
    st.write(f"**Reasoning:** {owner.explanation}")

    st.divider()
    st.markdown("##### ✍️ Ground-Truth Confirmation / Correction")
    st.caption("Help improve archaeological accuracy. Ground truth feedback is permanently recorded in the database.")

    col_c1, col_c2 = st.columns([1, 2])
    with col_c1:
        if st.button("✅ Confirm Correct Owner", use_container_width=True):
            db = SessionLocal()
            try:
                db_owner = db.query(DBOwner).filter(DBOwner.resource_id == res.id).first()
                if not db_owner:
                    db_owner = DBOwner(
                        resource_id=res.id,
                        name=owner.name,
                        team=owner.team,
                        email=owner.email,
                        confidence=owner.confidence.value,
                        source=owner.source.value,
                        explanation=owner.explanation
                    )
                    db.add(db_owner)
                db_owner.confirmed_by_user = True
                db.commit()
                st.success("Ownership confirmed and stored as ground truth!")
            finally:
                db.close()

    with col_c2:
        new_owner_input = st.text_input("Or assign corrected owner/team:", placeholder="e.g. SRE Platform Team")
        if st.button("💾 Submit Correction"):
            if new_owner_input.strip():
                db = SessionLocal()
                try:
                    db_owner = db.query(DBOwner).filter(DBOwner.resource_id == res.id).first()
                    if not db_owner:
                        db_owner = DBOwner(
                            resource_id=res.id,
                            name=new_owner_input.strip(),
                            confidence="HIGH",
                            source="owner_tag",
                            explanation="Human admin verified"
                        )
                        db.add(db_owner)
                    db_owner.confirmed_by_user = True
                    db_owner.user_correction = new_owner_input.strip()
                    db.commit()
                    st.success(f"Owner updated to '{new_owner_input.strip()}'!")
                finally:
                    db.close()
            else:
                st.warning("Please type a valid owner name.")

# ── Tab 3: Risk Verdict ──────────────────────────────────────────────────────
with tab3:
    st.markdown(f"#### Deletion Safety Verdict for `{res.id}`")

    if verdict.verdict_blocked:
        st.error(f"🛑 **VERDICT BLOCKED (INSUFFICIENT EVIDENCE)**: {verdict.block_reason}")
    elif verdict.risk_level == RiskLevel.LOW_RISK:
        st.success(f"🟢 **LOW RISK**: Safe to retire. Potential monthly saving: **${verdict.monthly_savings:.2f} / month**")
    elif verdict.risk_level == RiskLevel.MEDIUM_RISK:
        st.warning(f"🟡 **MEDIUM RISK**: Idle clues detected, but dependencies exist. Owner approval required. Potential saving: **${verdict.monthly_savings:.2f} / month**")
    else:
        st.error(f"🔴 **HIGH RISK**: Active production traffic or critical dependencies. Deletion NOT recommended.")

    col_v1, col_v2 = st.columns(2)
    with col_v1:
        st.markdown("##### ➕ Evidence FOR Deleting")
        if verdict.evidence_for:
            for f in verdict.evidence_for:
                st.markdown(f"- ✅ {f}")
        else:
            st.markdown("*- None.*")

    with col_v2:
        st.markdown("##### ➖ Evidence AGAINST Deleting")
        if verdict.evidence_against:
            for a in verdict.evidence_against:
                st.markdown(f"- ⚠️ {a}")
        else:
            st.markdown("*- None.*")

    st.markdown("##### 📋 Recommended Actions")
    for act in verdict.required_actions:
        st.markdown(f"- {act}")

# ── Tab 4: Quarantine & Decommission ─────────────────────────────────────────
with tab4:
    st.markdown(f"#### Reversible Decommissioning Workflow for `{res.id}`")
    st.caption("Never delete blindly. Take snapshots, isolate, watch for 14 days, and roll back immediately if dependencies alert.")

    db = SessionLocal()
    try:
        active_quar = db.query(DBQuarantine).filter(DBQuarantine.resource_id == res.id).order_by(DBQuarantine.initiated_at.desc()).first()

        col_q1, col_q2 = st.columns(2)

        with col_q1:
            st.markdown("##### 🚀 1. Initiate Reversible Quarantine")
            approver = st.text_input("Approving Engineer:", value="lead-sre@company.com", key="approver_input")
            watch_days = st.slider("Observation Watch Window (days):", min_value=7, max_value=60, value=14)

            if st.button("🛡️ Start Reversible Quarantine", type="primary", use_container_width=True):
                from mcp_tools.tools import start_safe_quarantine
                res_q = start_safe_quarantine(res.id, approver, watch_days)
                st.success(f"Resource placed in quarantine! Snapshot ID: `{res_q.get('snapshot_id')}`")
                st.rerun()

        with col_q2:
            st.markdown("##### ⏪ 2. Emergency Rollback")
            rollback_reason = st.text_input("Rollback Reason:", placeholder="e.g. Dependent batch job reported connection refused")

            if st.button("🚨 Roll Back Quarantine Immediately", use_container_width=True):
                if rollback_reason.strip():
                    from mcp_tools.tools import rollback_quarantine
                    res_rb = rollback_quarantine(res.id, rollback_reason.strip())
                    st.warning(f"Quarantine rolled back! State restored to `{res_rb.get('restored_state')}`.")
                    st.rerun()
                else:
                    st.warning("Please provide a rollback reason.")

        st.divider()
        st.markdown("##### 📜 Audit Trail & Workflow Logs")
        if active_quar:
            st.write(f"**Status:** `{active_quar.status}` | **Snapshot:** `{active_quar.snapshot_id}` | **Watch Until:** `{active_quar.watch_until}`")
            for log_line in active_quar.logs:
                st.code(log_line, language="text")
        else:
            st.info("No active quarantine workflow on this resource.")

    finally:
        db.close()

# ── Tab 5: Architecture & ER Workflow ───────────────────────────────────────
with tab5:
    st.markdown("#### 🗺️ Project Architecture, Pipeline Workflow & ER Diagrams")
    st.caption("Comprehensive blueprint of data flow, rule engines, database schemas, and state transitions.")

    view_mode = st.radio(
        "Select Diagram to Inspect:",
        [
            "💡 1. How the Core Idea Works (Technical Flowchart)",
            "🔄 2. End-to-End Pipeline & Engine Architecture",
            "🗄️ 3. Database Entity-Relationship (ER) Diagram",
            "👤 4. Owner Resolution Fallback Chain",
            "🛡️ 5. Reversible Quarantine State Machine"
        ],
        horizontal=True
    )

    if "1. How the Core Idea" in view_mode:
        st.markdown("##### 💡 Technical Flowchart: How the Archaeological Idea Works")
        st.markdown("""
```mermaid
flowchart TD
    classDef sourceStyle fill:#EBF5FB,stroke:#2980B9,stroke-width:2px,color:#1B4F72;
    classDef checkStyle fill:#FEF9E7,stroke:#F39C12,stroke-width:2px,color:#7D6608;
    classDef engineStyle fill:#E8F8F5,stroke:#16A085,stroke-width:2px,color:#0E6251;
    classDef decisionStyle fill:#FDEDEC,stroke:#C0392B,stroke-width:2px,color:#78281F;
    classDef safeStyle fill:#EAFAF1,stroke:#27AE60,stroke-width:2px,color:#145A32;

    %% 1. Ingestion Phase
    subgraph Phase1["📡 PHASE 1: Multi-Source Clue Gathering"]
        direction TB
        RawAWS["1. Query Cloud APIs<br/><code>boto3: ec2, ebs, sg</code><br/><i>Finds active & idle resources</i>"]:::sourceStyle
        RawCT["2. Ingest Audit Logs<br/><code>CloudTrail Events</code><br/><i>Who created/modified what & when</i>"]:::sourceStyle
        RawTF["3. Parse IaC State<br/><code>terraform.tfstate</code><br/><i>Maps code repository & module</i>"]:::sourceStyle
        RawGH["4. Interrogate Git & SCM<br/><code>GitHub PRs & CODEOWNERS</code><br/><i>Commit authors, PR merges, teams</i>"]:::sourceStyle
        RawCW["5. Network & Metric Signals<br/><code>CloudWatch & Flow Logs</code><br/><i>Network bytes, IOPS, last activity</i>"]:::sourceStyle
    end

    %% 2. Readiness Check
    subgraph Phase2["🛡️ PHASE 2: Signal Readiness & Sanity Check"]
        ReadinessGate{"Are required audit<br/>signals available?<br/><code>ReadinessChecker</code>"}:::checkStyle
        BlockWarning["Block or Degrade Verdict<br/><i>Rule: Never guess without evidence</i>"]:::decisionStyle
    end

    %% 3. Identity Linking
    subgraph Phase3["🔗 PHASE 3: Deterministic Identity Linking"]
        Linker["Resource Linker Engine<br/><code>linker.py</code><br/><i>Fuses all disjointed clues using <b>Resource ID</b> as Primary Key</i>"]:::engineStyle
        LinkedFactGraph[("Unified Archaeological Fact Graph<br/><code>LinkedResource</code>")]:::engineStyle
    end

    %% 4. The 3 Core Question Engines
    subgraph Phase4["🧠 PHASE 4: The 3 Core Reasoning Engines"]
        direction TB

        subgraph Q1["Question 1: Why does it exist?"]
            TBEngine["<b>Timeline Builder</b><br/><code>timeline_builder.py</code><br/>• Sort events chronologically<br/>• Detect out-of-band manual drift<br/>• Output: Complete Lifecycle Story"]:::engineStyle
        end

        subgraph Q2["Question 2: Who owns it?"]
            OREngine["<b>Owner Resolver</b><br/><code>owner_resolver.py</code><br/>• Fallback: Tags ➔ CODEOWNERS ➔ Account ➔ Creator<br/>• Assigns Confidence (HIGH/MED/LOW)<br/>• Output: Attributed Owner & Proof"]:::engineStyle
        end

        subgraph Q3["Question 3: Is it safe to delete?"]
            REEngine["<b>Risk & Dependency Engine</b><br/><code>risk_engine.py</code><br/>• Evaluate: Zero traffic + No IaC + No Inbound Bindings<br/>• Score: LOW / MED / HIGH / BLOCKED<br/>• Output: Concrete Evidence Pro/Con"]:::engineStyle
        end
    end

    %% 5. Human Decision & Safety State Machine
    subgraph Phase5["🛡️ PHASE 5: Safe Reversible Decommissioning"]
        VerdictCheck{"Risk Level & Owner Approval?"}:::checkStyle
        KeepActive["Keep Running<br/><i>(Resource is active/essential)</i>"]:::safeStyle
        
        subgraph QuarantineWorkflow["4-Stage Safety Isolation"]
            Snapshot["Step 1: Automated Snapshot<br/><code>Create EBS/AMI Backup</code>"]:::safeStyle
            IsolateSG["Step 2: Network Isolation<br/><code>Attach quarantine-sg (Deny Ingress)</code>"]:::safeStyle
            StopCompute["Step 3: Stop Instance<br/><code>EC2 Stopped (Billing Halts)</code>"]:::safeStyle
            CanaryWatch["Step 4: 14-Day Canary Observation<br/><code>Watch for alarm spikes / errors</code>"]:::safeStyle
        end

        RollbackTrigger{"Any dependency break<br/>or alert during 14 days?"}:::checkStyle
        EmergencyRollback["🚨 1-Click Rollback<br/><code>Instant state & network restore</code>"]:::decisionStyle
        FinalRetire["✅ Permanent Decommission<br/><code>Terminate resource (Retain snapshot)</code>"]:::safeStyle
    end

    %% Connections
    RawAWS & RawCT & RawTF & RawGH & RawCW --> ReadinessGate
    ReadinessGate -- "< 2 Signals" --> BlockWarning
    ReadinessGate -- "Coverage OK" --> Linker
    BlockWarning --> Linker
    Linker --> LinkedFactGraph
    LinkedFactGraph --> TBEngine & OREngine & REEngine

    TBEngine & OREngine & REEngine --> VerdictCheck
    VerdictCheck -- "HIGH RISK / In Use" --> KeepActive
    VerdictCheck -- "LOW / MED RISK + Approved" --> Snapshot
    Snapshot --> IsolateSG --> StopCompute --> CanaryWatch
    CanaryWatch --> RollbackTrigger
    RollbackTrigger -- "Yes (Problem detected)" --> EmergencyRollback
    RollbackTrigger -- "No (14 days silent)" --> FinalRetire
    EmergencyRollback --> KeepActive
```
        """)

    elif "2. End-to-End" in view_mode:
        st.markdown("##### 🔄 End-to-End Archaeological Pipeline")
        st.markdown("""
```mermaid
flowchart TD
    subgraph DataSources["📡 1. Multi-Source Ingestion Layer"]
        AWS["AWS Boto3 (EC2, EBS, SG)"]
        CT["CloudTrail (Audit Logs)"]
        TF["Terraform State (.tfstate)"]
        GH["GitHub (PRs, Commits, CODEOWNERS)"]
        CW["CloudWatch / VPC Flow Logs"]
    end

    subgraph CoreEngine["⚙️ 2. Core Archaeological Engine"]
        RC["Readiness Checker<br/><i>(Audits Signal Availability)</i>"]
        LK["Resource Linker<br/><i>(Joins by Resource ID)</i>"]
        TB["Timeline Builder<br/><i>(Chronological Story)</i>"]
        OR["Owner Resolver<br/><i>(5-Step Fallback Chain)</i>"]
        RE["Risk Engine<br/><i>(Rule-Based Safety Evaluation)</i>"]
    end

    subgraph StorageLayer["🗄️ 3. SQLite / PostgreSQL DB"]
        DB[(SQLAlchemy Models)]
    end

    subgraph DeliveryLayer["🚀 4. Interfaces & Automation"]
        API["FastAPI REST API"]
        MCP["MCP Server Tools"]
        UI["Streamlit Dashboard"]
        AGENT["watsonx / ICA AI Agent"]
        QUAR["Reversible Quarantine Engine"]
    end

    AWS & CT & TF & GH & CW --> RC
    RC --> LK
    LK --> TB & OR & RE
    TB & OR & RE --> DB
    DB --> API
    API --> MCP & UI
    MCP --> AGENT
    UI & AGENT --> QUAR
```
        """)

    elif "2. Database" in view_mode:
        st.markdown("##### 🗄️ Database Entity-Relationship (ER) Schema")
        st.markdown("""
```mermaid
erDiagram
    RESOURCES ||--o{ EVENTS : "has audit trail (1:N)"
    RESOURCES ||--o| OWNERS : "attributed to (1:1)"
    RESOURCES ||--o{ RISK_VERDICTS : "evaluated by (1:N)"
    RESOURCES ||--o{ QUARANTINES : "undergoes (1:N)"

    RESOURCES {
        string id PK "Resource ID (e.g. i-0a8b9c...)"
        string name "Resource tag name"
        string resource_type "ec2_instance | ebs_volume | security_group"
        string region "AWS Region"
        datetime created_at "Launch / Creation timestamp"
        text tags_json "JSON Key-Value tags"
        string state "running | stopped | available"
        float cost_per_month "Estimated monthly cost ($)"
        text details_json "Hardware, IPs, Security details"
        text attached_to_json "Parent/Child bindings"
        text dependencies_json "Inbound/Outbound dependencies"
        datetime created_in_db "Ingestion timestamp"
    }

    EVENTS {
        string id PK "Event / Transaction UUID"
        string resource_id FK "References resources.id"
        datetime timestamp "Event occurrence time"
        string event_type "RunInstances | ModifySecurityGroup | etc."
        string actor "IAM User / Role / GitHub Bot"
        string source "CLOUDTRAIL | GITHUB | TERRAFORM | MANUAL"
        text description "Human readable event story"
        text metadata_json "Raw audit payload"
    }

    OWNERS {
        int id PK "Auto-increment ID"
        string resource_id FK "References resources.id (UNIQUE)"
        string name "Attributed Owner / Team"
        string team "Department or SRE Pod"
        string email "Owner Email address"
        string confidence "HIGH | MEDIUM | LOW"
        string source "owner_tag | codeowners | account_owner | creator | unowned"
        text explanation "Deterministic audit reason"
        boolean confirmed_by_user "Ground truth confirmed"
        string user_correction "Manual override name"
        datetime updated_at "Last verified timestamp"
    }

    RISK_VERDICTS {
        int id PK "Auto-increment ID"
        string resource_id FK "References resources.id"
        string risk_level "LOW_RISK | MEDIUM_RISK | HIGH_RISK | BLOCKED"
        float monthly_savings "Potential $ reclaimed"
        text evidence_for_json "Array of facts supporting deletion"
        text evidence_against_json "Array of blocker facts"
        text missing_evidence_json "Signals unavailable"
        boolean verdict_blocked "True if evidence < threshold"
        text block_reason "Reason verdict was blocked"
        text required_actions_json "Next actionable remediation steps"
        datetime assessed_at "Assessment timestamp"
    }

    QUARANTINES {
        string id PK "Quarantine Workflow UUID"
        string resource_id FK "References resources.id"
        string status "none | isolated | stopped | snapshot_created | retired | restored"
        datetime initiated_at "Start timestamp"
        string approved_by "Authorizing Engineer"
        string snapshot_id "EBS / Instance backup ID"
        text previous_state_json "Pre-isolation configuration"
        int watch_period_days "Observation window (default: 14)"
        datetime watch_until "Retirement deadline"
        boolean problem_detected "Triggered alert flag"
        text problem_details "Diagnostic error logs"
        text logs_json "Chronological action audit trail"
    }
```
        """)

    elif "3. Owner" in view_mode:
        st.markdown("##### 👤 5-Tier Fallback Chain for Ownership Resolution")
        st.markdown("""
```mermaid
flowchart TD
    Start([Resource Ingested]) --> Step1{1. Resource 'Owner' Tag?}
    Step1 -- Yes --> HighTag[Assign Tagged Owner<br/><b>Confidence: HIGH</b>]
    Step1 -- No --> Step2{2. Terraform & CODEOWNERS?}

    Step2 -- Yes --> HighCode[Assign Repo Owner<br/><b>Confidence: HIGH</b>]
    Step2 -- No --> Step3{3. Account / Team Tag?}

    Step3 -- Yes --> MedAccount[Assign Account Owner<br/><b>Confidence: MEDIUM</b>]
    Step3 -- No --> Step4{4. CloudTrail Creator Active?}

    Step4 -- Yes --> MedCreator[Assign Creator<br/><b>Confidence: MEDIUM</b>]
    Step4 -- No --> Step5[Send to Review Queue<br/><b>Confidence: LOW (Unowned)</b>]

    HighTag & HighCode & MedAccount & MedCreator & Step5 --> GroundTruth[Human Admin Confirmation / Correction]
```
        """)

    elif "4. Reversible" in view_mode:
        st.markdown("##### 🛡️ 4-Stage Reversible Quarantine Decommissioning Workflow")
        st.markdown("""
```mermaid
stateDiagram-v2
    [*] --> Active : Resource in Normal Operation
    Active --> QuarantineInitiated : Human Approves Deletion
    
    state QuarantineInitiated {
        [*] --> BackupCreated : Create Automated Snapshot
        BackupCreated --> Isolated : Strip Ingress / Isolate Network
        Isolated --> Stopped : Stop Compute (Cost Drops)
    }

    QuarantineInitiated --> ObservationWatch : Start 14-60 Day Watch Period

    state ObservationWatch {
        Monitoring : Monitor Logs & Alarms
        CheckDependencies : Verify No Connection Refused Errors
    }

    ObservationWatch --> PermanentRetirement : 14 Days Pass With 0 Incidents
    PermanentRetirement --> [*] : Final Delete (Snapshot Retained)

    ObservationWatch --> EmergencyRollback : Dependency Alert / Human Abort
    EmergencyRollback --> Active : 1-Click Instant Restore From Snapshot
```
        """)
