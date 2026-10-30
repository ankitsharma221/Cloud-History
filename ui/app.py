"""Streamlit Web UI Dashboard for Cloud Resource Archaeologist.

Interactive UI for exploring cloud resource provenance, ownership, risk verdicts,
and executing reversible decommissioning workflows.
"""

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
is_production = os.getenv("APP_ENV", "development").lower() == "production"
aws_collector = AWSCollector(region_name=os.getenv("AWS_REGION", "ap-south-1"), use_seed=not is_production)
cloudtrail_collector = CloudTrailCollector(region_name=os.getenv("AWS_REGION", "ap-south-1"), use_seed=not is_production)

linker = Linker(aws_collector=aws_collector, cloudtrail_collector=cloudtrail_collector)
timeline_builder = TimelineBuilder()
owner_resolver = OwnerResolver()
risk_engine = RiskEngine()
readiness_checker = ReadinessChecker(aws_collector=aws_collector, cloudtrail_collector=cloudtrail_collector)

# ── Sidebar ──────────────────────────────────────────────────────────────────

st.sidebar.title("🔍 Resource Archaeologist")
st.sidebar.caption("Evidence-in. Safe decisions out.")

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

st.sidebar.markdown(f"**Environment:** `{'AWS Live (ap-south-1)' if is_production else 'Seed / Dev Mode'}`")

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
tab1, tab2, tab3, tab4 = st.tabs([
    "📜 1. Why Does It Exist? (Timeline)",
    "👤 2. Who Owns It? (Ownership)",
    "⚖️ 3. Can We Delete It? (Risk Verdict)",
    "🛡️ 4. Safe Reversible Quarantine"
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
