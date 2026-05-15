"""
Core agent: connects to one or more MCP servers, exposes their tools to Claude,
and runs the agentic tool-use loop. Maintains conversation history across turns.
"""

import os
from contextlib import AsyncExitStack
from dotenv import load_dotenv
import anthropic
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

load_dotenv("../.env")

MODEL = "claude-sonnet-4-6"

SYSTEM_PROMPT = """You are a personal running coach assistant for Shantanu.
You have access to his Strava running data through tools.
When planning or analyzing:
- Always fetch his recent runs and stats before making recommendations
- Be specific with distances, paces, and days of the week
- Account for recovery — don't suggest hard efforts on back-to-back days
- Keep responses concise and actionable
Today's date: {today}"""


class MCPAgent:
    """
    Agent that connects to multiple MCP servers and uses Claude to reason
    over their combined tools. Maintains conversation history across turns.
    Add new MCP servers by passing additional URLs to the constructor.
    """

    def __init__(self, mcp_server_urls: list[str]):
        self.server_urls = mcp_server_urls
        self._client = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self._messages: list[dict] = []
        self._session_map: dict[str, ClientSession] = {}
        self._tools: list[dict] = []
        self._stack: AsyncExitStack | None = None

    async def __aenter__(self):
        self._stack = AsyncExitStack()
        await self._stack.__aenter__()

        for url in self.server_urls:
            read, write, _ = await self._stack.enter_async_context(
                streamablehttp_client(url)
            )
            session = await self._stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            self._session_map[url] = session

        self._tools = await self._collect_tools()
        return self

    async def __aexit__(self, *args):
        await self._stack.__aexit__(*args)

    async def _collect_tools(self) -> list[dict]:
        tools = []
        for session in self._session_map.values():
            result = await session.list_tools()
            for tool in result.tools:
                tools.append({
                    "name": tool.name,
                    "description": tool.description or "",
                    "input_schema": tool.inputSchema,
                })
        return tools

    async def _call_tool(self, name: str, arguments: dict) -> str:
        for session in self._session_map.values():
            listed = await session.list_tools()
            if any(t.name == name for t in listed.tools):
                result = await session.call_tool(name, arguments)
                return "\n".join(
                    item.text for item in result.content if hasattr(item, "text")
                )
        return f"Tool '{name}' not found on any connected server."

    async def chat(self, user_message: str) -> str:
        from datetime import date
        system = SYSTEM_PROMPT.format(today=date.today().strftime("%A, %B %d %Y"))

        self._messages.append({"role": "user", "content": user_message})

        while True:
            response = await self._client.messages.create(
                model=MODEL,
                max_tokens=4096,
                system=system,
                tools=self._tools,
                messages=self._messages,
            )

            if response.stop_reason == "end_turn":
                text = next(
                    (b.text for b in response.content if hasattr(b, "text")), ""
                )
                self._messages.append({"role": "assistant", "content": text})
                return text

            if response.stop_reason == "tool_use":
                # Store assistant turn (includes tool_use blocks)
                assistant_content = []
                for block in response.content:
                    if block.type == "text":
                        assistant_content.append({"type": "text", "text": block.text})
                    elif block.type == "tool_use":
                        assistant_content.append({
                            "type": "tool_use",
                            "id": block.id,
                            "name": block.name,
                            "input": block.input,
                        })
                self._messages.append({"role": "assistant", "content": assistant_content})

                # Execute tools and collect results
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        result = await self._call_tool(block.name, block.input)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        })
                self._messages.append({"role": "user", "content": tool_results})

            else:
                return "Unexpected stop reason. Please try again."

    def reset(self):
        """Clear conversation history to start a fresh session."""
        self._messages.clear()
