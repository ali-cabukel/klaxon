"""LangGraph incident agent with MCP / in-process tools."""

from __future__ import annotations

import logging
import re
import sys
from pathlib import Path
from typing import Annotated, Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from typing_extensions import TypedDict

from klaxon.settings import get_settings

log = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are Klaxon, an incident desk operator answering inside Slack. "
    "Use tools to query and update the incident database. Never invent issue IDs. "
    "For analytics, call issue_stats or search_issues rather than guessing. "
    "After writes or simulated GitHub actions, confirm what changed and cite "
    "public_id / side-effect details. Be concise (1-3 short paragraphs). "
    "Use Slack mrkdwn: *bold*, _italic_, `code`, and <url|label> links. "
    "Never use Markdown headings or tables."
)


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]


def to_mrkdwn(text: str) -> str:
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"<\2|\1>", text)
    text = re.sub(r"(?<!\*)\*\*(?!\*)(.+?)(?<!\*)\*\*(?!\*)", r"*\1*", text)
    text = re.sub(r"^#{1,6}\s*(.+)$", r"*\1*", text, flags=re.MULTILINE)
    return text


def extract_reply_text(messages: list[BaseMessage]) -> str:
    for message in reversed(messages):
        if isinstance(message, AIMessage):
            content = message.content
            if isinstance(content, str) and content.strip():
                return to_mrkdwn(content)
            if isinstance(content, list):
                parts = [
                    block.get("text", "")
                    for block in content
                    if isinstance(block, dict) and block.get("type") == "text"
                ]
                text = "".join(parts).strip()
                if text:
                    return to_mrkdwn(text)
    return "I couldn't produce a reply."


_tools_cache: list[Any] | None = None
_mcp_client: Any | None = None


async def _load_tools() -> list[Any]:
    """Load agent tools (in-process by default; MCP stdio when KLAXON_USE_MCP=1)."""
    global _tools_cache, _mcp_client
    if _tools_cache is not None:
        return _tools_cache

    settings = get_settings()
    use_mcp = settings.mcp_url == "stdio" or __import__("os").environ.get(
        "KLAXON_USE_MCP", ""
    ).lower() in {"1", "true", "yes"}

    if use_mcp:
        try:
            from langchain_mcp_adapters.client import MultiServerMCPClient

            server_path = Path(__file__).resolve().parents[1] / "mcp" / "server.py"
            _mcp_client = MultiServerMCPClient(
                {
                    "klaxon": {
                        "transport": "stdio",
                        "command": sys.executable,
                        "args": [str(server_path)],
                    }
                }
            )
            _tools_cache = await _mcp_client.get_tools()
            log.info("loaded %d tools via MCP stdio", len(_tools_cache))
            return _tools_cache
        except Exception:
            log.exception("MCP tool load failed; falling back to in-process tools")

    from klaxon.agent.tools import build_tools

    _tools_cache = build_tools()
    log.info("loaded %d in-process tools", len(_tools_cache))
    return _tools_cache


async def _build_graph(tools: list[Any]):
    settings = get_settings()
    from langchain_anthropic import ChatAnthropic

    llm = ChatAnthropic(
        model=settings.agent_model,
        api_key=settings.anthropic_api_key,
        temperature=0,
    ).bind_tools(tools)

    def call_llm(state: AgentState):
        return {"messages": [llm.invoke(state["messages"])]}

    def should_continue(state: AgentState):
        last = state["messages"][-1]
        return "tools" if getattr(last, "tool_calls", None) else END

    graph = StateGraph(AgentState)
    graph.add_node("llm", call_llm)
    graph.add_node("tools", ToolNode(tools))
    graph.set_entry_point("llm")
    graph.add_conditional_edges("llm", should_continue)
    graph.add_edge("tools", "llm")
    return graph.compile()


async def run_agent(
    prompt: str,
    *,
    history: list[dict[str, str]] | None = None,
    user_id: str = "",
    team_id: str = "",
) -> str:
    """Answer a user prompt. Echo mode when no Anthropic key is set."""
    settings = get_settings()
    if not settings.agent_enabled:
        return _echo(prompt)

    try:
        tools = await _load_tools()
        graph = await _build_graph(tools)
        messages: list[BaseMessage] = [SystemMessage(content=SYSTEM_PROMPT)]
        for turn in history or []:
            role = turn.get("role", "user")
            content = turn.get("content", "")
            if role == "assistant":
                messages.append(AIMessage(content=content))
            else:
                messages.append(HumanMessage(content=content))
        messages.append(HumanMessage(content=prompt))
        result = await graph.ainvoke({"messages": messages})
        return extract_reply_text(result["messages"])
    except Exception:
        log.exception("agent call failed user=%s team=%s", user_id, team_id)
        return "I couldn't reach the model just now. Please try again."


def _echo(prompt: str) -> str:
    return (
        "*Echo backend active.*\n"
        f"You said: {prompt}\n\n"
        "_Set `ANTHROPIC_API_KEY` and `AGENT_MODEL` to use the incident agent._"
    )
