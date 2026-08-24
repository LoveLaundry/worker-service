# Worker Service

Isolated microservice that tracks **laundry staff daily tasks** for Love Laundry.

## What it records

- **Worker registry** — name, department/role, phone, active status.
- **Daily task logs** — per worker per day:
  - Shift & attendance (present / half day / absent / leave), check-in / check-out, overtime.
  - Work done broken down by task type: washing, pressing (ironing), folding, packing, dry cleaning, stain treatment, machine cleaning, delivery support and other ad-hoc tasks — each with quantity + unit (pieces / kg / loads).
  - Weight of laundry handled (kg).
  - Quality issues: rewash count, damaged items, customer complaints.
  - Machines/equipment used, chemicals/consumables used.
  - Supervisor notes and a computed productivity figure (pieces per hour).

## Security

- Same JWT bearer authentication as the other services (`JWT_SECRET` shared with user-service).
- Role based access control (`ADMIN`, `MANAGER`, `STAFF`).
- All worker/task data is encrypted at rest with AES-256-GCM envelope encryption (`MASTER_KEY`).

## Environment variables

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | MongoDB / PostgreSQL / SQLite connection URL |
| `MONGODB_MAIN_URI` / `MONGODB_MAIN_DB` | Production source-of-truth database |
| `JWT_SECRET` | Shared JWT signing secret |
| `MASTER_KEY` | Master key for field-level encryption |
| `ALLOWED_ORIGINS` | CORS origins |

## Run locally

```bash
uv sync
uvicorn src.worker_service.main:app --reload --port 8003
```
