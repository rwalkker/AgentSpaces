# Remmy Shift Planner Agent v1.1

AI-powered shift planning partner for CRET (16-role) and AR/WHD (3-role) operations at PHX6.

## Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Configure database
cp .env.example .env
# Edit .env with your Render PostgreSQL connection string:
# DATABASE_URL=postgresql://user:password@host:port/dbname
# If DATABASE_URL is not set, falls back to local SQLite (remmy.db)

# Run
python remmy.py
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string (Render) | `sqlite:///remmy.db` |

## What Remmy Does

- Generates Day/Night headcount plans for CRET + AR/WHD
- Applies 4-week rolling average UPH with quarterly adjustments
- Enforces positioning strategy (On Course / Underprocess / Overprocess)
- Validates 22+ guardrail flags across 3 severity tiers
- Tracks overrides with downstream cascade recalculation
- Learns from shift outcomes to improve accuracy over time
- Exports to PDF, CSV, and Slack format

## Architecture

```
remmy/
├── remmy.py              # CLI entry point
├── remmy/
│   ├── db.py             # PostgreSQL/SQLite connection
│   ├── models/           # SQLAlchemy ORM models
│   ├── engine/           # Volume, rate, HC, positioning, dilution
│   ├── conversation/     # Intent parsing, session state, Q&A
│   ├── guardrails/       # Flag engine, overrides, v1.2/v1.3 addenda
│   ├── learning/         # Rolling averages, override patterns, metrics
│   └── export/           # Artifact renderer, PDF/CSV/Slack export
├── Dockerfile
├── requirements.txt
└── .env.example
```

## Spec Coverage

- v1.1: Core engine, CRET 16-role, AR/WHD 3-role, positioning, flags, overrides, learning loop
- v1.2: Disposition routing, CALM codes, indirect staffing rules, key metrics
- v1.3: Policy-defined indirect ratios, ambassador activation, EOS quality targets, RACI escalation
