# Deployment And Demo Runbook

This runbook is for a hackathon reviewer or operator who needs to repeat the
DossierAgent deployment and demo from a clean VM.

Source-of-truth spec sections:

- `Deploiement sur VM GCP`
- `Demo et seeds`
- `Script de demo sur trois minutes`

## VM Shape

Use one VM for the MVP. SQLite is the operational source of truth and must stay
on one local disk attached to one machine.

| Area | Recommendation |
|---|---|
| OS | Ubuntu LTS or Debian stable |
| CPU/RAM | 4 vCPU, 16 GB RAM |
| Disk | 50-100 GB balanced persistent disk |
| Runtime | Docker Engine with the Compose plugin |
| App path | `/srv/dossieragent/app` |
| Data path | `/srv/dossieragent/app/data` and `/srv/dossieragent/app/storage` |
| Public access | Prefer SSH tunnel or HTTPS reverse proxy; do not expose raw Kibana publicly |

## Docker Install

On a fresh Ubuntu/Debian VM:

```bash
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-plugin git curl
sudo usermod -aG docker "$USER"
newgrp docker
docker --version
docker compose version
```

## Clone And Environment

```bash
sudo mkdir -p /srv/dossieragent
sudo chown "$USER:$USER" /srv/dossieragent
cd /srv/dossieragent
git clone https://github.com/Zacxxx/DossierAgent.git app
cd app
cp .env.example .env
```

Before running a shared or public demo, replace the local development secrets in
`.env`:

```bash
python3 - <<'PY'
from pathlib import Path
from secrets import token_hex

path = Path(".env")
text = path.read_text()
replacements = {
    "ELASTIC_PASSWORD": token_hex(24),
    "KIBANA_SYSTEM_PASSWORD": token_hex(24),
    "KIBANA_ENCRYPTION_KEY": token_hex(32),
    "DOSSIERAGENT_CRON_SECRET": token_hex(24),
    "DOSSIERAGENT_CONTAINER_UID": str(__import__("os").getuid()),
    "DOSSIERAGENT_CONTAINER_GID": str(__import__("os").getgid()),
}
for key, value in replacements.items():
    text = "\n".join(
        f"{key}={value}" if line.startswith(f"{key}=") else line
        for line in text.splitlines()
    )
path.write_text(text + "\n")
PY
```

## Compose Startup

```bash
docker compose up -d --build
docker compose ps
curl -fsS http://127.0.0.1:8000/health
```

The `seed` service runs before the API starts and writes deterministic demo data
to `./data` and generated files to `./storage`.

Local URLs:

- Frontend: `http://127.0.0.1:5173`
- API: `http://127.0.0.1:8000`
- Kibana: `http://127.0.0.1:5601`
- Elasticsearch: `http://127.0.0.1:9200`

For review over SSH without opening raw ports:

```bash
ssh -L 5173:127.0.0.1:5173 -L 8000:127.0.0.1:8000 -L 5601:127.0.0.1:5601 user@VM_IP
```

Then open `http://127.0.0.1:5173` locally.

## Backup And Snapshot Discipline

SQLite is single-machine state. Do not run multiple API containers or multiple
VMs against the same database file, and do not put `data/dossieragent.db` on a
shared network filesystem.

Cold backup:

```bash
cd /srv/dossieragent/app
docker compose down
tar -czf "$HOME/dossieragent-backup-$(date +%Y%m%d-%H%M).tgz" data storage .env
docker compose up -d
```

Hot backup rule: if you back up while the API is running, copy the SQLite
database file together with any `-wal` and `-shm` files. A cold backup is simpler
and safer for the demo.

On GCP, also take persistent disk snapshots before the public demo and after any
manual data curation:

```bash
gcloud compute disks snapshot DISK_NAME \
  --zone=ZONE \
  --snapshot-names=dossieragent-demo-$(date +%Y%m%d-%H%M)
```

## Three-Minute Demo Script

Start from a clean seeded state:

```bash
docker compose run --rm seed
docker compose up -d
```

Open the frontend at `http://127.0.0.1:5173`.

| Time | Action | What To Show |
|---|---|---|
| 0:00 | Dashboard | Active Toulouse watch, next scan, dossier score, checks, notifications |
| 0:20 | Trigger run | Run the API command below, then refresh dashboard |
| 0:45 | Run summary | 24 candidates, 8 duplicates, 4 reposts, 4 useful new listings |
| 1:05 | Listings | Open `Annonces`; show reasons, risks, score, and recommended status |
| 1:35 | Contact packet | Open `Paquets`; generate packet; show draft, questions, and pending check |
| 2:00 | Dossier | Open `Dossier`; show valid documents, missing docs, and run analysis |
| 2:25 | History | Show run events from the API command below |
| 2:45 | Conclusion | The agent assists; the user validates before sensitive action |

Run-now command:

```bash
RUN_ID=$(curl -fsS -X POST http://127.0.0.1:8000/api/v1/market-watches/watch_toulouse_t2/run-now \
  -H "Idempotency-Key: demo-run-$(date +%s)" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["run_id"])')
echo "$RUN_ID"
```

Run events command:

```bash
curl -fsS "http://127.0.0.1:8000/api/v1/agent-runs/${RUN_ID}/events" | python3 -m json.tool
```

Automated smoke check:

```bash
bun run test:e2e
```

The E2E command seeds isolated local state under `test-results/e2e-state`, starts
the API and Vite on test ports, exercises the visible demo path, and keeps
Playwright traces for failures.
