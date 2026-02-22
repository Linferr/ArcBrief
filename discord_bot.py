"""Discord bot for ArcBrief (Phase 1)."""

import asyncio
import os
from typing import Any, Dict, List, Optional

import aiohttp
import discord
from discord import app_commands


API_BASE = os.getenv("ARCBRIEF_API_BASE", "http://localhost:8000/api")
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")
API_KEY = os.getenv("ARCBRIEF_API_KEY", "arcbrief-local-dev-key")


async def api_get(path: str) -> Any:
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{API_BASE}{path}",
            headers={"X-API-Key": API_KEY},
        ) as res:
            if res.status >= 400:
                raise RuntimeError(f"GET {path} failed: {res.status}")
            return await res.json()


async def api_post(path: str, payload: Optional[Dict[str, Any]] = None) -> Any:
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{API_BASE}{path}",
            json=payload,
            headers={"Content-Type": "application/json", "X-API-Key": API_KEY},
        ) as res:
            if res.status >= 400:
                raise RuntimeError(f"POST {path} failed: {res.status}")
            return await res.json()


def chunk_text(text: str, size: int = 1800) -> List[str]:
    return [text[i : i + size] for i in range(0, len(text), size)]


class ArcBriefBot(discord.Client):
    def __init__(self):
        super().__init__(intents=discord.Intents.default())
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()


bot = ArcBriefBot()


@bot.tree.command(name="topics", description="List ArcBrief topics with status")
async def list_topics(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)
    try:
        topics = await api_get("/topics")
        if not topics:
            await interaction.followup.send("No topics yet. Create one in the web UI.")
            return
        lines = []
        for t in topics:
            status = "active" if t.get("is_active") else "paused"
            lines.append(f"- [{status}] {t['id']} | {t['name']}")
        await interaction.followup.send("\n".join(lines))
    except Exception as e:
        await interaction.followup.send(f"Failed to load topics: {e}")


@bot.tree.command(name="brief", description="Get latest brief for a topic")
@app_commands.describe(topic_id="Topic ID shown in /topics")
async def latest_brief(interaction: discord.Interaction, topic_id: int):
    await interaction.response.defer(thinking=True)
    try:
        brief = await api_get(f"/briefs/{topic_id}/latest")
        content = brief.get("content", "")
        if not content:
            await interaction.followup.send("No brief content.")
            return
        await interaction.followup.send(f"**Latest Brief · {brief.get('date','')}**")
        for chunk in chunk_text(content):
            await interaction.channel.send(f"```markdown\n{chunk}\n```")
    except Exception as e:
        await interaction.followup.send(f"Failed to get brief: {e}")


@bot.tree.command(name="research", description="Run a deep research query")
@app_commands.describe(query="Research question")
async def research(interaction: discord.Interaction, query: str):
    await interaction.response.defer(thinking=True)
    try:
        run = await api_post("/run", {"query": query})
        run_id = run.get("run_id")
        if not run_id:
            await interaction.followup.send("Failed to start run.")
            return

        await interaction.followup.send(f"Started research: `{run_id}`. Polling for completion...")

        report = ""
        for _ in range(180):
            status = await api_get(f"/status/{run_id}")
            if status.get("report_content"):
                report = status.get("report_content", "")
            if status.get("status") == "done":
                break
            await asyncio.sleep(2)

        if not report:
            await interaction.channel.send("No report content yet.")
            return

        await interaction.channel.send("**Research Report**")
        for chunk in chunk_text(report):
            await interaction.channel.send(f"```markdown\n{chunk}\n```")

    except Exception as e:
        await interaction.followup.send(f"Research failed: {e}")


@bot.tree.command(name="ask", description="Ask a question about recent news briefs")
@app_commands.describe(
    question="Your question (e.g. 'What happened with OpenAI this week?')",
    topic="Optional topic filter: 'ai', 'policy', 'global', 'macro'",
)
async def ask(interaction: discord.Interaction, question: str, topic: Optional[str] = None):
    await interaction.response.defer(thinking=True)
    topic_id = None
    if topic:
        try:
            topics = await api_get("/topics")
            matches = [t for t in topics if topic.lower() in t["name"].lower()]
            if matches:
                topic_id = matches[0]["id"]
        except Exception:
            pass  # topic filter is optional; proceed without it

    try:
        result = await api_post("/chat", {"message": question, "topic_id": topic_id})
        reply = result.get("reply", "No relevant information found.")
        sources = result.get("sources", [])
        response = reply
        if sources:
            response += f"\n\n*Sources: {', '.join(sources)}*"
    except Exception as e:
        response = f"Error fetching answer: {e}"

    for chunk in chunk_text(response):
        await interaction.followup.send(chunk)


@bot.tree.command(name="digest", description="Get the latest brief summary for each active topic")
async def digest(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)
    try:
        data = await api_get("/briefs/recent?limit=40")
        items = data.get("items", [])
        # One per topic — list is ordered by created_at DESC, first occurrence = latest
        seen: Dict[int, Any] = {}
        for b in items:
            tid = b.get("topic_id")
            if tid is not None and tid not in seen:
                seen[tid] = b
        if not seen:
            await interaction.followup.send("No briefs available yet.")
            return
        lines = [
            f"**{b['topic_name']}** ({b.get('date', 'N/A')})"
            for b in seen.values()
        ]
        await interaction.followup.send("\n".join(lines))
    except Exception as e:
        await interaction.followup.send(f"Error: {e}")


def main():
    if not DISCORD_TOKEN:
        raise RuntimeError("DISCORD_TOKEN not set")
    bot.run(DISCORD_TOKEN)


if __name__ == "__main__":
    main()
