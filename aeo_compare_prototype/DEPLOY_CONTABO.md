# Deploying the AEO Comparison app to Contabo (Docker, no CI/CD, no Nginx)

Step-by-step guide to run this app on your existing Contabo VPS as a Docker
container, reachable directly at `http://<VPS_IP>:8200`.

No CI/CD. No domain. No reverse proxy. You write the `.env` by hand on the VPS.

**This app is fully self-contained.** Everything it needs is inside this one
folder (the analysis/parsing/metrics code and the brand-centric `poc/` code are
vendored in under `config/`, `services/`, `repos/`, `poc/`, `models/`, `db/`,
`prompts/`, `utils/`). There is **no dependency on `cron_server` or any other
service.** You push just this folder to a new repo.

> **Empty database is fine (client-demo path).** A fresh VPS Mongo has no
> business profiles, so the `DEFAULT_BUSINESS_ID` prefill won't resolve — that's
> expected and non-fatal. The client just types the business context (name,
> brand names, industry, products) directly in the UI and tracks prompts from
> there. `DEFAULT_BUSINESS_ID` is only a convenience for pre-loading a known
> profile; leave it as-is or blank. Comparison sessions are saved to the
> `aeo_compare_sessions` collection, which Mongo creates automatically.

---

## Quick start (TL;DR)

Assumes MongoDB is already installed and running on the VPS (as you said it is).
MongoDB defaults to `mongodb://localhost:27017` in code, so you only need the API
keys in `.env`.

```bash
# 1. Install Docker (skip if already installed)
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER          # then log out & back in

# 2. Get the code
sudo mkdir -p /opt/aeo-compare && sudo chown $USER:$USER /opt/aeo-compare
cd /opt/aeo-compare
git clone <your-repo-url> .

# 3. Create the .env (only API keys are required — see Step 5 for the template)
nano .env

# 4. Build and run (host networking → reaches local Mongo + serves on the VPS IP)
docker build -t aeo-compare:latest .
docker run -d --name aeo-compare --restart unless-stopped \
  --network host --env-file .env aeo-compare:latest

# 5. Open the firewall for the web port
sudo ufw allow 8200/tcp

# 6. Check it
sudo docker logs -f aeo-compare
curl -s localhost:8200/api/providers
```

Then browse to `http://<VPS_IP>:8200`. The detailed sections below explain each
step and the alternatives.

---

## 1. Prerequisites on the VPS (verify once)

SSH into your Contabo box and confirm Docker + Mongo are present:

```bash
# Docker installed and running?
docker --version
sudo systemctl status docker --no-pager | head -5

# MongoDB reachable on the host?
sudo systemctl status mongod --no-pager | head -5      # if installed as a service
ss -lntp | grep 27017                                  # should show something LISTENing on 27017
```

If `docker` is missing (Ubuntu/Debian):

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER      # then log out & back in so `docker` works without sudo
```

> **Assumption:** Mongo runs **natively on the host** (the usual
> `apt install mongodb-org` setup listening on `127.0.0.1:27017`). If your Mongo
> is itself a Docker container, see **Appendix B**.

---

## 2. Container/repo files (already included)

These three files ship **in this folder already** — you don't need to create
anything. They're reproduced here for reference so you know what's in the image
and the repo. Skip ahead to Step 3 if you just want to deploy.

### 2.1 `Dockerfile`

```dockerfile
# Python 3.11 is required: the code uses datetime.UTC (3.11+) and PEP 604
# "X | None" unions.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install deps first for better layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the whole self-contained app (app code + vendored packages + static).
COPY . .

# Informational only (ignored when using --network host, which we recommend).
EXPOSE 8200

# No --reload in production. Bind 0.0.0.0 so it's reachable on the VPS IP.
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8200"]
```

> If `pip install` ever fails on the slim image because a package wants to
> compile from source, add build tools before the pip line:
> ```dockerfile
> RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
>     && rm -rf /var/lib/apt/lists/*
> ```
> With the pinned versions in `requirements.txt` you almost certainly won't need
> this — they all ship prebuilt wheels — but it's here if you do.

### 2.2 `.dockerignore`

```
__pycache__/
*.pyc
venv/
.env
.git/
```

### 2.3 `.gitignore`

```
__pycache__/
*.pyc
venv/
.env
```

> **Critical:** `.env` is git-ignored and docker-ignored on purpose. Secrets
> never go into the repo or the image. You place `.env` on the VPS by hand
> (Step 5) and inject it at `docker run` time (Step 6).

---

## 3. Push to a new GitHub repo

From inside this folder:

```bash
cd backend/aeo_compare_prototype

git init
git add .
git status                     # SANITY CHECK: confirm NO .env and NO venv are staged
git commit -m "Standalone AEO comparison app"

# Create the repo on GitHub (web UI or gh CLI), then:
git remote add origin git@github.com:<you>/zicy-aeo-compare.git
git branch -M main
git push -u origin main
```

> Make the GitHub repo **private** — it contains your business/parsing logic. No
> secrets are in it (you verified `.env` isn't staged), but private is safer.

---

## 4. Clone the code onto the VPS

```bash
ssh <user>@<VPS_IP>

sudo mkdir -p /opt/aeo-compare
sudo chown $USER:$USER /opt/aeo-compare
cd /opt/aeo-compare

git clone git@github.com:<you>/zicy-aeo-compare.git .
# or HTTPS:  git clone https://github.com/<you>/zicy-aeo-compare.git .
```

---

## 5. Write the `.env` on the VPS (by hand)

Create `/opt/aeo-compare/.env`:

```bash
cd /opt/aeo-compare
nano .env
```

Paste and fill in real values. **Only the API keys are required** — MongoDB
defaults to a local install (`mongodb://localhost:27017`, db `zicy_tools`), which
`--network host` reaches directly, so you don't need Mongo settings here at all:

```dotenv
# --- OpenAI (REQUIRED — used for BOTH instructor parses; parsing model is gpt-5-mini) ---
OPENAI_API_KEY=sk-...

# --- DataForSEO (REQUIRED — fetches the answer-engine responses) ---
DATAFORSEO_LOGIN=your_login
DATAFORSEO_PASSWORD=your_password

# --- MongoDB (OPTIONAL — defaults are baked in; only set to override) ---
# MONGODB_URI=mongodb://localhost:27017
# MONGODB_DB_NAME=zicy_tools

# --- Optional model overrides ---
# GEMINI_MODEL=gemini-2.5-flash
# PERPLEXITY_MODEL=sonar-reasoning
# DATAFORSEO_BASE_URL=https://api.dataforseo.com/v3
```

Lock down permissions:

```bash
chmod 600 /opt/aeo-compare/.env
```

> **How the env is consumed:** `docker run --env-file .env` injects these as real
> process environment variables, which the app reads via `os.getenv(...)`. The
> app's `load_dotenv()` call looks for a local `.env` file inside the container;
> it won't find one and does nothing — that's fine, the injected vars are what
> matter.
>
> `--env-file` caveat: plain `KEY=VALUE` per line — do **not** wrap values in
> quotes, and avoid trailing spaces. Your values (URI, keys) are fine as-is.

---

## 6. Build and run the container

From `/opt/aeo-compare` (where the `Dockerfile` is):

```bash
# 6.1 — build the image
docker build -t aeo-compare:latest .

# 6.2 — run it (host networking = simplest for your setup)
docker run -d \
  --name aeo-compare \
  --restart unless-stopped \
  --network host \
  --env-file /opt/aeo-compare/.env \
  aeo-compare:latest
```

Why `--network host` (recommended for you):
- `MONGODB_URI=mongodb://localhost:27017` reaches your host Mongo directly. (A
  bridge-network container's `localhost` is the container itself, not the host —
  it would fail to connect.)
- uvicorn binds the host's `0.0.0.0:8200`, so `http://<VPS_IP>:8200` works with
  **no `-p` port mapping and no Nginx**. Exactly your requirement.

Check it's up:

```bash
docker ps                                # STATUS should say "Up"
docker logs -f aeo-compare               # watch startup; Ctrl-C to stop watching
curl -s localhost:8200/api/providers     # should return JSON with providers
```

---

## 7. Open the firewall for port 8200

The app has **no authentication**, and every "Analyze" spends money on OpenAI +
DataForSEO. Don't leave it open to the whole internet unless you mean to.

**Recommended — restrict to your own IP:**

```bash
sudo ufw allow from <YOUR_HOME_OR_OFFICE_IP> to any port 8200 proto tcp
sudo ufw reload
sudo ufw status
```

**Or, open to everyone (only if you accept the risk):**

```bash
sudo ufw allow 8200/tcp
sudo ufw reload
```

> - Keep Mongo private: **never** run `ufw allow 27017`.
> - Contabo also has an *external* firewall in their web panel (usually off by
>   default). If you've enabled it, add a TCP 8200 rule there too, or `ufw`
>   alone won't be enough.

Now browse to: **`http://<VPS_IP>:8200`**

---

## 8. Everyday operations

```bash
# View logs
docker logs -f aeo-compare

# Restart / stop / start
docker restart aeo-compare
docker stop aeo-compare
docker start aeo-compare

# Redeploy after you push new code to GitHub
cd /opt/aeo-compare
git pull
docker build -t aeo-compare:latest .
docker rm -f aeo-compare
docker run -d --name aeo-compare --restart unless-stopped \
  --network host --env-file /opt/aeo-compare/.env aeo-compare:latest

# Free disk from old images occasionally
docker image prune -f
```

---

## Appendix A — Alternative: bridge networking (instead of `--network host`)

Only use this if you specifically don't want host networking.

```bash
docker run -d \
  --name aeo-compare \
  --restart unless-stopped \
  -p 8200:8200 \
  --add-host=host.docker.internal:host-gateway \
  --env-file /opt/aeo-compare/.env \
  aeo-compare:latest
```

And in `.env`, point Mongo at the host:

```dotenv
MONGODB_URI=mongodb://host.docker.internal:27017
```

Extra requirement: your host `mongod` must listen on an interface the container
can reach (not just `127.0.0.1`) — you'd set `bindIp` in `/etc/mongod.conf` to
include the Docker bridge gateway (e.g. `172.17.0.1`) and firewall it to the
Docker subnet only. This is exactly the complexity `--network host` avoids.

---

## Appendix B — If your MongoDB is itself a Docker container

Put both containers on the same user-defined network and connect by name.

```bash
# Assuming your mongo container is named "mongo" and already running:
docker network create zicy-net 2>/dev/null || true
docker network connect zicy-net mongo

docker run -d \
  --name aeo-compare \
  --restart unless-stopped \
  --network zicy-net \
  -p 8200:8200 \
  --env-file /opt/aeo-compare/.env \
  aeo-compare:latest
```

`.env`:

```dotenv
MONGODB_URI=mongodb://mongo:27017
```

(Here you use `-p 8200:8200` for the web port since you're not on host
networking.)

---

## Troubleshooting

| Symptom | Cause / Fix |
|---|---|
| App starts but every request times out on Mongo | Wrong network mode. The default `mongodb://localhost:27017` only reaches host Mongo under `--network host`. Use that, or see Appendix A/B. |
| `RuntimeError: OpenAI client not initialized` on Analyze | `OPENAI_API_KEY` missing/blank in `.env`. |
| Can't reach `http://<VPS_IP>:8200` in a browser but `curl localhost:8200` works on the VPS | Firewall. Open port 8200 (Step 7) and check the Contabo web-panel firewall. |
| `Business <id> not found` on load | `DEFAULT_BUSINESS_ID` doesn't exist in your `MONGODB_DB_NAME`. Non-fatal — set a real id, or ignore and type fields manually in the UI. |
| Container keeps restarting | `docker logs aeo-compare` to see the crash; usually a missing env var or a non-3.11 base image. |
