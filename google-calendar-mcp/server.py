"""
Google Calendar MCP Server.
Exposes calendar scheduling tools for run planning.

Local:      http://localhost:8002/mcp
Cloud Run:  https://<service>.run.app/mcp
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from mcp.server.fastmcp import FastMCP
from tools.schedule import (
    get_week_events, get_free_slots, get_busy_days,
    create_run_events, get_agent_run_events, edit_run_event,
)

PORT = int(os.getenv("PORT", "8002"))
HOST = "0.0.0.0"

mcp = FastMCP(
    name="google-calendar-mcp",
    instructions=(
        "You have access to the user's Google Calendar, including their personal "
        "and college (CMU) calendars. Use these tools to understand their weekly "
        "schedule, identify free windows suitable for running, and create or edit "
        "planned run events. Only create events after the user explicitly approves "
        "the proposed plan. Only edit events that were created by this agent."
    ),
    host=HOST,
    port=PORT,
)

mcp.tool()(get_week_events)
mcp.tool()(get_free_slots)
mcp.tool()(get_busy_days)
mcp.tool()(create_run_events)
mcp.tool()(get_agent_run_events)
mcp.tool()(edit_run_event)

if __name__ == "__main__":
    print(f"Starting Google Calendar MCP server on http://{HOST}:{PORT} ...")
    mcp.run(transport="streamable-http")
