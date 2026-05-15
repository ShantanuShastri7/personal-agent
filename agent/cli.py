"""
CLI interface for the agent. Run this to chat with the agent locally.
The Strava MCP server must already be running on port 8001.

Usage:
    python cli.py

Commands during chat:
    /reset   - clear conversation history
    /quit    - exit
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from agent import MCPAgent

MCP_SERVERS = [
    "https://strava-mcp-86893833347.us-central1.run.app/mcp",
    # Add more MCP server URLs here as you build them:
    # "https://google-mcp-86893833347.us-central1.run.app/mcp",
]


async def main():
    print("Connecting to MCP servers...")

    async with MCPAgent(mcp_server_urls=MCP_SERVERS) as agent:
        print(f"Connected. Tools loaded: {[t['name'] for t in agent._tools]}")
        print("\nRunning Coach Agent ready. Type your message or /quit to exit.\n")

        while True:
            try:
                user_input = input("You: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nGoodbye!")
                break

            if not user_input:
                continue

            if user_input == "/quit":
                print("Goodbye!")
                break

            if user_input == "/reset":
                agent.reset()
                print("Conversation history cleared.\n")
                continue

            print("Agent: ", end="", flush=True)
            response = await agent.chat(user_input)
            print(response)
            print()


if __name__ == "__main__":
    asyncio.run(main())
