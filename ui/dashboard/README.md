# LegionTrap Dashboard

React dashboard for LegionTrap TI. Proxies all `/api/*` requests to the backend API at `http://127.0.0.1:8088`.

## Start

```bash
npm install   # first time only
npm run dev   # dashboard at http://localhost:5173
```

## Login

Use the credentials set in your `.env` file:

- **Username:** value of `DASH_USER`
- **Password:** the plaintext password whose bcrypt hash is stored in `DASH_PASS`

See the main [README.md](../../README.md) Quick Start for instructions on generating the bcrypt hash.

## Views

| View | Description |
|------|-------------|
| Events | All ingested events, newest first |
| Campaigns | Grouped behavioral campaigns with lifecycle status (active, dormant, historical) |
| Actors | Operator-assigned actor profiles linked to one or more campaigns |
| AI Summaries | Narrative analysis generated on request (requires `AI_BACKEND` to be configured in `.env`) |
| IOC Export | Firewall block lists in UFW and pf.conf formats |

## Empty state

A fresh database shows empty views in Events, Campaigns, and Actors. To populate with synthetic demo data, run `scripts/seed_demo.sh` from the project root — see the main README for safety warnings and instructions. Do not run the seed script against a database that contains real sensor data.

## Tech stack

React 19 · TypeScript · Vite 7 · Recharts · Vite dev-server proxy
