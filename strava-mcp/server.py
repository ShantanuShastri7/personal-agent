"""
Strava MCP Server.
Exposes Strava running data as MCP tools for the agent.

Local:      http://localhost:8001/mcp
Cloud Run:  https://<service>.run.app/mcp  (PORT env var set by GCP)
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from mcp.server.fastmcp import FastMCP
from tools.activities import get_recent_runs, get_athlete_stats, get_athlete_profile

# Cloud Run sets PORT automatically. Locally defaults to 8001.
# Host is always 0.0.0.0 so the container accepts external connections.
PORT = int(os.getenv("PORT", "8001"))
HOST = "0.0.0.0"

mcp = FastMCP(
    name="strava-mcp",
    instructions=(
        "You have access to the user's Strava running data. "
        "Use these tools to retrieve recent runs, overall stats, and profile information "
        "to help plan training schedules and analyze performance."
    ),
    host=HOST,
    port=PORT,
)

mcp.tool()(get_recent_runs)
mcp.tool()(get_athlete_stats)
mcp.tool()(get_athlete_profile)

if __name__ == "__main__":
    print(f"Starting Strava MCP server on http://{HOST}:{PORT} ...")
    mcp.run(transport="streamable-http")
