# Personal Agent

A personal AI running coach that connects to your Strava data and helps you plan your weekly training schedule. Interact with it via a Telegram bot on your phone.

## Architecture

```
[Telegram App]
      ↓
[Agent Service]  ←  Claude API (claude-sonnet-4-6)
      ↓
[Strava MCP Server]  →  Strava API
[Google MCP Server]  →  Google Calendar + Gmail  (coming soon)
```

- **MCP Servers** run on GCP Cloud Run (scale to zero when idle)
- **Agent** runs locally and connects to the cloud MCP servers
- **Telegram bot** is the mobile interface

## Project Structure

```
personal-agent/
├── strava-mcp/          # MCP server: Strava running data
│   ├── server.py        # FastMCP HTTP server (port 8001 local / 8080 cloud)
│   ├── strava_client.py # Strava API wrapper with auto token refresh
│   ├── gcp_secrets.py   # Secret abstraction: .env locally, Secret Manager on cloud
│   ├── tools/
│   │   └── activities.py  # get_recent_runs, get_athlete_stats, get_athlete_profile
│   ├── setup_auth.py    # One-time Strava OAuth setup
│   ├── upload_secrets.py # One-time: push .env secrets to GCP Secret Manager
│   ├── Dockerfile
│   └── requirements.txt
├── agent/
│   ├── agent.py         # Core agent: MCP client + Claude agentic loop
│   ├── cli.py           # Local CLI interface for testing
│   └── requirements.txt
└── package.json         # MCP Inspector (dev tool)
```

## Local Setup

### Prerequisites
- Python 3.13+
- Node.js 18+
- A [Strava API app](https://www.strava.com/settings/api)
- An [Anthropic API key](https://console.anthropic.com)

### 1. Configure secrets

Copy `.env.example` to `.env` and fill in your values:

```
STRAVA_CLIENT_ID=
STRAVA_CLIENT_SECRET=
STRAVA_ACCESS_TOKEN=       # populated by setup_auth.py
STRAVA_REFRESH_TOKEN=      # populated by setup_auth.py
STRAVA_TOKEN_EXPIRES_AT=   # populated by setup_auth.py
ANTHROPIC_API_KEY=
TELEGRAM_BOT_TOKEN=        # from @BotFather on Telegram
```

### 2. Authorize Strava (one time)

```bash
cd strava-mcp
pip install -r requirements.txt
python setup_auth.py
```

### 3. Run the Strava MCP server

```bash
cd strava-mcp
python server.py
# Listening on http://localhost:8001
```

### 4. Run the agent

```bash
cd agent
pip install -r requirements.txt
python cli.py
```

### 5. Debug with MCP Inspector

```bash
npm install
npm run inspect
# Open http://localhost:6274, connect to http://localhost:8001/mcp
```

## GCP Deployment (Strava MCP Server)

The MCP server is deployed to Cloud Run and scales to zero when not in use.

### One-time setup

```bash
# Authenticate
gcloud auth login
gcloud config set project personal-agent-496411

# Enable APIs
gcloud services enable secretmanager.googleapis.com run.googleapis.com artifactregistry.googleapis.com

# Upload secrets
cd strava-mcp
GOOGLE_CLOUD_PROJECT=personal-agent-496411 python upload_secrets.py

# Create Artifact Registry repo
gcloud artifacts repositories create mymcp \
  --repository-format=docker \
  --location=us-central1

# Grant Cloud Run access to secrets
gcloud projects add-iam-policy-binding personal-agent-496411 \
  --member="serviceAccount:86893833347-compute@developer.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

### Deploy

```bash
cd strava-mcp

docker build --platform=linux/amd64 \
  -t us-central1-docker.pkg.dev/personal-agent-496411/mymcp/strava-mcp:latest .

docker push us-central1-docker.pkg.dev/personal-agent-496411/mymcp/strava-mcp:latest

gcloud run deploy strava-mcp \
  --image=us-central1-docker.pkg.dev/personal-agent-496411/mymcp/strava-mcp:latest \
  --platform=managed \
  --region=us-central1 \
  --allow-unauthenticated \
  --set-env-vars GOOGLE_CLOUD_PROJECT=personal-agent-496411
```

**Live URL:** `https://strava-mcp-86893833347.us-central1.run.app`

## Roadmap

- [x] Strava MCP server
- [x] Local CLI agent
- [x] Deploy Strava MCP to GCP Cloud Run
- [ ] Google Calendar + Gmail MCP server
- [ ] Telegram bot interface
- [ ] Deploy agent to Cloud Run
