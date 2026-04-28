# Streamlit Cloud Deployment Guide

## Repo architecture

```
tourhero-data/pipeline/dashboard/   ← SOURCE OF TRUTH (private, github.com/tourhero/tourhero-data)
tourhero-dashboard/                 ← STREAMLIT DEPLOY REPO (private, github.com/andres-lizarazo-th/tourhero-dashboard)
```

Both repos live on your Desktop at `~/Desktop/Tourhero/`. Dashboard code is developed in `tourhero-data` and synced to `tourhero-dashboard` using `deploy.sh`. Streamlit Cloud watches `tourhero-dashboard` and redeploys automatically on every push.

**Never edit files directly in `tourhero-dashboard/`** — they will be overwritten on the next deploy.

---

## Day-to-day workflow

### 1 — Make changes in tourhero-data

Edit any file inside `pipeline/dashboard/` as normal.

### 2 — Deploy to Streamlit Cloud

```bash
cd ~/Desktop/Tourhero/tourhero-data/pipeline/dashboard
bash deploy.sh                          # auto commit message
bash deploy.sh "feat: add new chart"    # custom commit message
bash deploy.sh --dry-run                # preview what would change
```

The script:
1. `rsync`s all dashboard files to `~/Desktop/Tourhero/tourhero-dashboard/`
2. Commits and pushes to `github.com/andres-lizarazo-th/tourhero-dashboard`
3. Streamlit Cloud picks up the push and redeploys (usually < 2 min)

**Live URL:** https://tourhero-dashboardgtm.streamlit.app

### 3 — Also commit to tourhero-data (source of truth)

```bash
cd ~/Desktop/Tourhero/tourhero-data
git add pipeline/dashboard/
git commit -m "feat(dashboard): ..."
git push origin develop
```

---

## Local development

```bash
cd pipeline/dashboard
pip install -r requirements.txt
streamlit run Home.py
```

The app reads BigQuery credentials from the project root `.env`:
```
GCP_PROJECT_ID=creator-outreach-database
GOOGLE_APPLICATION_CREDENTIALS=secrets/gcp-service-account.json
BQ_LOCATION=southamerica-east1
```

## Deploy to Streamlit Community Cloud

### 1 — Create a service account for the dashboard

Use a separate service account from any production loader so you can rotate credentials independently.

GCP Console → **IAM & Admin** → **Service accounts** → **Create service account**:
- Name: `looker-streamlit-reader` (or similar)
- Roles: **BigQuery Data Viewer** + **BigQuery Job User** (project-wide is fine; tighten later if needed)
- Keys → **Add key** → **JSON** → save the file (you'll paste its contents into Streamlit secrets)

### 2 — Push the dashboard code to a GitHub repo

The repo can be private. Make sure `.gitignore` excludes:
- `secrets/`
- `.env`
- `dashboard/.streamlit/secrets.toml`

The file `dashboard/.streamlit/secrets.toml.example` IS committed (template only — no real keys).

### 3 — Create the app on Streamlit Cloud

Go to https://share.streamlit.io → **New app** → connect GitHub.

| Setting | Value |
|---|---|
| Repository | your fork / org repo |
| Branch | `main` (or whichever) |
| Main file path | `pipeline/dashboard/Home.py` |
| Python version | 3.11 |

### 4 — Paste secrets

In the app settings → **Secrets** → paste this format:

```toml
GCP_PROJECT_ID = "creator-outreach-database"
BQ_LOCATION    = "southamerica-east1"

[gcp_service_account]
type                       = "service_account"
project_id                 = "creator-outreach-database"
private_key_id             = "..."
private_key                = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
client_email               = "looker-streamlit-reader@creator-outreach-database.iam.gserviceaccount.com"
client_id                  = "..."
auth_uri                   = "https://accounts.google.com/o/oauth2/auth"
token_uri                  = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url        = "..."
```

Take the JSON file from step 1, copy each field as a string in TOML format above. **Important:** TOML escapes newlines in `private_key` as literal `\n`. Streamlit's TOML parser will convert them back when reading.

### 5 — Restrict access (recommended)

Streamlit Cloud apps are public by default. To gate access:
- Settings → **Sharing** → **Only people with access** → add team emails

### 6 — Verify

After deploy, the Home page shows a "freshness footer" that confirms BQ connectivity. If it loads numbers, you're good.

---

## Cost expectations

- BigQuery: see Home page for query volumes — typical session ≈ 1 GB scanned; first 1 TB/month free.
- Streamlit Cloud: free tier supports community apps (limit on resources but adequate for ≤ 20 concurrent users).
- For heavier traffic or stricter access controls, deploy on Cloud Run with IAP instead.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| "Could not load freshness footer" | Service account missing `bigquery.jobs.create` or `bigquery.tables.getData` | Re-check IAM roles |
| "Unrecognized name: ..." | View has been re-deployed with renamed columns | Pull latest `dashboard/` and re-deploy |
| Charts blank but no error | Date range selected has no data | Adjust range — Bison data starts 2025-Q4 |
| `to_dataframe` permission error | Service account missing `bigquery.readsessions.create` for the BQ Storage API | Either grant the role OR confirm `create_bqstorage_client=False` is in `utils/bq.py` (already set) |
