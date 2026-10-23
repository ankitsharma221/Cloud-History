# Cloud Resource Archaeologist

> Know why every cloud resource exists. Retire it safely.

---

## What It Does

Answers 3 questions about any AWS cloud resource:
1. **Why does it exist?** — Full history timeline from creation to today.
2. **Who owns it?** — Current owner with confidence level.
3. **Is it safe to delete?** — Rule-based verdict with evidence. Never auto-deletes.

---

## Project Structure

```
cloud-resource-archaeologist/
├── PLAN.md                    ← Full build plan (read this first)
├── engine/                    ← The brain: collects, links, calculates
│   ├── models.py              ← Data shapes
│   ├── linker.py              ← Joins all sources
│   ├── timeline_builder.py    ← Builds history
│   ├── owner_resolver.py      ← Finds owner
│   ├── risk_engine.py         ← Risk verdict
│   ├── readiness_checker.py   ← Signal availability
│   └── collectors/            ← One file per data source
├── db/                        ← Storage + seed data
├── api/                       ← FastAPI REST server
├── mcp_tools/                 ← MCP tools for AI agent
├── agent/                     ← ICA agent config
└── tests/                     ← Automated tests
```

---

## Quick Start

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Set up environment
```bash
cp .env.example .env
# Edit .env if you have real AWS credentials.
# Leave blank to use fake/seed data (default for development).
```

### 3. Set up the database and load seed data
```bash
python -m db.database
```

### 4. Run the API
```bash
uvicorn api.main:app --reload
```

API docs available at: http://localhost:8000/docs

### 5. Launch the Web UI Dashboard
```bash
streamlit run ui/app.py
```

Dashboard available at: http://localhost:8501

### 6. Run tests
```bash
pytest -v
```

---

## Development Mode (No Real AWS)

By default the project runs on **seed data** — realistic fake AWS resources in `db/seed_data/`.
No AWS account, no credentials, no cost needed.

The 5 fake resources included:
| Name | Type | Story |
|---|---|---|
| payment-api-prod | EC2 | Active, owned, Terraform-managed |
| old-analytics-server | EC2 | Idle 60 days, owner left |
| vol-orphaned-001 | EBS | Unattached, no activity |
| dev-test-instance | EC2 | Manual creation, unknown owner |
| sg-legacy-open | Security Group | Wide-open ports, 3 years old |

---

## Build Order

See [PLAN.md](PLAN.md) for the full step-by-step build plan.

Steps: Models → Seed Data → Database → Collectors → Linker →
Timeline → Owner Resolver → Risk Engine → Readiness Checker →
API → MCP Tools → Agent → Tests

---

## Tech Stack

- **Python 3.11+** — FastAPI, boto3, Pydantic v2, SQLAlchemy
- **moto** — Fake AWS for testing (no real account needed)
- **SQLite** → PostgreSQL for production
- **MCP Python SDK** — Agent-agnostic tool interface
- **IBM ICA / watsonx** — AI agent layer

---

*Evidence in. Safe decisions out.*
