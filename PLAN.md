# Cloud Resource Archaeologist — Full Build Plan

---

## What Are We Building? (Plain English)

A tool that answers 3 questions about any cloud resource (like an AWS server or disk):

1. **Why does it exist?** → Shows the full history: who created it, from which code, when, and what changed since.
2. **Who owns it?** → Finds the current owner, not just who created it.
3. **Is it safe to delete?** → Gives a verdict with real evidence. Never guesses. Never deletes automatically.

If the owner approves, the tool retires the resource in a safe, reversible way with a full audit trail.

---

## The Problem We Are Solving

Companies run thousands of cloud resources. Over time:
- Projects end, teams change, people leave — but resources keep running.
- Nobody knows why a resource exists or who owns it.
- Nobody wants to delete it in case it breaks something.
- Result: wasted money every month, forever.

The hard part is not finding idle resources. It is knowing whether it is **safe to remove one**.

---

## How It Works (Simple Flow)

```
User asks a question
       ↓
AI Agent receives the question
       ↓
Agent calls the Engine (via MCP tools)
       ↓
Engine collects clues from:
  → AWS (what resources exist)
  → CloudTrail (who created/changed them)
  → Terraform (is it managed by code?)
  → GitHub (which PR/commit created it?)
  → CloudWatch (is it being used?)
       ↓
Engine links all clues by resource ID
       ↓
Engine builds a timeline + finds owner + calculates risk
       ↓
Agent explains the result in plain language
       ↓
User approves → staged retirement begins
```

---

## What We Will Build — 3 Parts

### Part A: The Engine (Backend)
The brain. Collects data, links it, stores it, and calculates answers.
This is most of the work.

### Part B: The API
A simple web server that exposes the engine as HTTP endpoints.
The agent and the UI talk to this.

### Part C: The Agent
An AI that talks to the engine and explains results in plain language.
The agent does NOT guess — it only explains what the engine found.

---

## Folder Structure

```
cloud-resource-archaeologist/
│
├── PLAN.md                          ← This file
├── README.md                        ← How to run the project
├── requirements.txt                 ← Python packages needed
├── .env.example                     ← Environment variables template
│
├── engine/                          ← The brain
│   ├── __init__.py
│   ├── models.py                    ← Data shapes (what a Resource, Event, Owner looks like)
│   ├── linker.py                    ← Joins all sources by resource ID
│   ├── timeline_builder.py          ← Builds history timeline per resource
│   ├── owner_resolver.py            ← Finds owner using fallback chain
│   ├── risk_engine.py               ← Rule-based risk verdict
│   ├── readiness_checker.py         ← Checks which signals are available
│   │
│   └── collectors/                  ← One file per data source
│       ├── __init__.py
│       ├── aws_collector.py         ← Reads EC2, EBS, Security Groups
│       ├── cloudtrail_collector.py  ← Reads audit events (who did what)
│       ├── terraform_collector.py   ← Reads Terraform state file
│       └── github_collector.py      ← Reads Git commits and pull requests
│
├── db/                              ← Storage
│   ├── __init__.py
│   ├── database.py                  ← SQLite setup (PostgreSQL later)
│   ├── models_db.py                 ← Database table definitions
│   │
│   └── seed_data/                   ← Fake but realistic data for dev + demo
│       ├── ec2_instances.json       ← 5 fake EC2 instances
│       ├── ebs_volumes.json         ← 3 fake EBS volumes
│       ├── security_groups.json     ← 4 fake security groups
│       ├── cloudtrail_events.json   ← Fake audit log events
│       ├── terraform_state.json     ← Fake Terraform state
│       └── github_prs.json          ← Fake pull requests
│
├── api/                             ← FastAPI web server
│   ├── __init__.py
│   └── main.py                      ← All API endpoints
│
├── mcp_tools/                       ← MCP tool layer (connects engine to AI agent)
│   ├── __init__.py
│   └── tools.py                     ← get_provenance(), get_risk_verdict(), etc.
│
├── agent/                           ← AI Agent config
│   ├── agent-orchestration.yaml     ← ICA deployment config
│   └── prompts.py                   ← System prompts
│
└── tests/                           ← Automated tests
    ├── __init__.py
    ├── test_collectors.py           ← Tests for data collectors
    ├── test_risk_engine.py          ← Tests for risk verdict rules
    └── test_owner_resolver.py       ← Tests for owner fallback chain
```

---

## Build Order — Step by Step

We build ONE thing at a time. Each step works before we move to the next.

---

### STEP 1 — Data Models (`engine/models.py`)
**What:** Python classes that define the shape of every piece of data.
**Why first:** Everything else depends on agreeing on what a Resource, Event, Owner looks like.

Key models:
- `Resource` — id, type, name, region, created_at, tags, state, cost_per_month
- `Event` — resource_id, timestamp, event_type, actor, source, description
- `Owner` — resource_id, name, team, confidence, source
- `RiskVerdict` — resource_id, risk_level, evidence_for, evidence_against, verdict_blocked
- `Timeline` — resource_id, list of Events in time order

---

### STEP 2 — Seed Data (`db/seed_data/*.json`)
**What:** Realistic fake JSON files for 5 cloud resources.
**Why:** We have no real AWS account. This data drives everything — engine, API, agent, demo.

The 5 fake resources:

| # | Type | Name | Story |
|---|---|---|---|
| 1 | EC2 | payment-api-prod | Created by pipeline, has traffic, owned by Payments team |
| 2 | EC2 | old-analytics-server | Created 2 years ago, no traffic for 60 days, owner left |
| 3 | EBS | vol-orphaned-001 | Not attached to any instance, no activity |
| 4 | EC2 | dev-test-instance | Created manually, no Terraform, unknown owner |
| 5 | Security Group | sg-legacy-open | Wide open ports, created manually 3 years ago |

---

### STEP 3 — Database (`db/database.py` + `db/models_db.py`)
**What:** SQLite database with tables for resources, events, owners, verdicts, audit trail.
**Why:** Engine needs a place to store and query linked facts.

---

### STEP 4 — Collectors (`engine/collectors/`)
**What:** One Python file per data source. Each reads its source and returns structured data.

| Collector | Reads From | Returns |
|---|---|---|
| aws_collector.py | Seed JSON (moto in tests) | List of Resource objects |
| cloudtrail_collector.py | Seed JSON | List of Event objects |
| terraform_collector.py | terraform_state.json | Dict of resource_id → terraform info |
| github_collector.py | github_prs.json | Dict of commit_id → PR info |

---

### STEP 5 — Linker (`engine/linker.py`)
**What:** Joins all collector outputs using resource ID as the key.
**Output:** One complete picture per resource — AWS info + audit events + Terraform + GitHub all together.

---

### STEP 6 — Timeline Builder (`engine/timeline_builder.py`)
**What:** Takes a linked resource and produces a sorted list of events — the full history.
**Output example:**
```
MAR 14 → Created by pipeline payment-deploy (PR #142, GitHub)
APR 02 → Resized by pipeline (CloudTrail)
JUN 18 → Security group modified MANUALLY — outside pipeline (CloudTrail)
SEP 29 → Last deployment (GitHub Actions)
```

---

### STEP 7 — Owner Resolver (`engine/owner_resolver.py`)
**What:** Finds the current owner using a fallback chain.
**Why:** Creator ≠ owner. Person deploys in 2022, leaves in 2023. Resource still needs an owner.

Fallback order:
```
1. owner tag on the resource        → High confidence
2. CODEOWNERS file in the repo      → High confidence
3. Account owner                    → Medium confidence
4. Creator, only if still active    → Medium confidence
5. Review queue (unknown)           → Low confidence
```
Each answer says which step it came from.

---

### STEP 8 — Risk Engine (`engine/risk_engine.py`)
**What:** Rule-based verdict. Answers "Can I delete this?" with reasons.
**Rules:**

| Check | Evidence FOR deleting | Evidence AGAINST |
|---|---|---|
| Terraform managed? | Not in Terraform state | In state = someone intentionally manages it |
| Dependencies? | No references found | Referenced by load balancer, IAM role |
| Traffic? | 0 requests for 21+ days | Recent traffic detected |
| Last used? | Not used for 30+ days | Used recently |
| Evidence coverage | 4+ clues found | < 2 clues = verdict BLOCKED |

**Verdict levels:**
- `LOW RISK` — all signals say safe to remove
- `MEDIUM RISK` — mixed signals, owner must approve
- `HIGH RISK` — strong signals against deletion
- `BLOCKED` — not enough evidence to rate

---

### STEP 9 — Readiness Checker (`engine/readiness_checker.py`)
**What:** Checks what data signals are available before giving any verdict.
**Output example:**
```
CloudTrail:     ✅ Enabled (90 days)
AWS Config:     ❌ Not enabled
VPC Flow Logs:  ❌ Not enabled
Terraform:      ✅ Found (47 resources)
GitHub:         ✅ Connected

Coverage: 3 of 5 signals. Traffic verdict will be BLOCKED (Flow Logs missing).
```

---

### STEP 10 — FastAPI Engine (`api/main.py`)
**What:** REST API that exposes the engine as HTTP endpoints.

Endpoints:
```
GET  /readiness                       → readiness report
GET  /resources                       → list all resources
GET  /resources/{id}/provenance       → full timeline
GET  /resources/{id}/verdict          → risk verdict
POST /resources/{id}/quarantine       → start staged retirement
POST /resources/{id}/rollback         → undo quarantine
GET  /resources/{id}/audit            → full audit trail
```

---

### STEP 11 — MCP Tools (`mcp_tools/tools.py`)
**What:** Wraps the FastAPI engine as MCP tools so an AI agent can call them.

Tools:
```
get_provenance(resource_id)      → timeline
get_risk_verdict(resource_id)    → verdict with reasons
get_readiness_report()           → signal availability
start_quarantine(resource_id)    → staged retirement
rollback_quarantine(resource_id) → undo
```

---

### STEP 12 — ICA Agent (`agent/agent-orchestration.yaml`)
**What:** Deploy the agent on IBM ICA platform.
**Why:** IBM-internal pitch. Agent answers in plain language backed by engine evidence.

---

### STEP 13 — Tests (`tests/`)
**What:** Automated tests.
- Collectors work with fake data
- Linker joins correctly
- Owner resolver picks right fallback
- Risk engine gives right verdict
- API returns correct responses

---

## Technology Stack

| What | Technology | Why |
|---|---|---|
| Language | Python 3.11+ | Everything we need has a Python library |
| AWS SDK | boto3 | Standard AWS client |
| Fake AWS (dev/test) | moto | No real AWS account needed |
| Data validation | Pydantic v2 | Every fact is validated before storage |
| Database | SQLite → PostgreSQL | SQLite for now, easy to upgrade |
| ORM | SQLAlchemy 2.0 | Clean database access |
| DB migrations | Alembic | Change schema without losing data |
| Web server | FastAPI | Fast, auto-docs at /docs |
| MCP layer | MCP Python SDK | Agent talks to engine via tools |
| AI model | watsonx / ICA | IBM-approved, safe for company data |
| UI | Streamlit | Fast to build for demo |
| Testing | pytest + moto | Test without real AWS |
| Dependency graph | NetworkX | Map what depends on what |

---

## What We Are NOT Building (MVP)

| Skipped | Why |
|---|---|
| Azure / GCP | AWS only. Data model stays cloud-neutral for later. |
| Slack / Jira | Phase 2 |
| S3 and RDS retirement | Phase 2 |
| Automatic deletion | Never. Human always approves. |
| RAG over PR text | Phase 2. Structured facts first. |
| CMDB / ServiceNow | Phase 2 |

---

## The Golden Rule

> **The tool must never sound more confident than the evidence allows.**
> When evidence is thin → say "I don't know."
> When a signal is missing → block the verdict.
> "I don't know" is a feature, not a failure.

---

*Build one step at a time. Test each step. Move only when it works.*
