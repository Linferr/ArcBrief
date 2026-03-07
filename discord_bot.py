"""Discord bot for ArcBrief (Phase 1)."""

import asyncio
import os
import time
from typing import Any, Dict, List, Optional

import aiohttp
import discord
from discord import app_commands

from discord_bot_api import build_api_error_message
from discord_bot_formatting import (
    format_bookmark_action_message,
    format_analyze_mobile_message,
    chunk_text,
    format_ask_mobile_message,
    format_brief_mobile_message,
    format_long_task_status_message,
    format_saved_mobile_message,
    format_digest_mobile_message,
    format_research_mobile_message,
    format_tldr_mobile_message,
)
from discord_bot_helpers import resolve_topic_reference


API_BASE = os.getenv("ARCBRIEF_API_BASE", "http://localhost:8000/api")
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")
API_KEY = os.getenv("ARCBRIEF_API_KEY", "arcbrief-local-dev-key")
CONFIG_CACHE_TTL_SECONDS = 300
LANGUAGE_MAP = {
    "en": "English (US)",
    "zh": "Chinese (Simplified)",
    "ja": "Japanese",
}


async def api_get(path: str) -> Any:
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{API_BASE}{path}",
            headers={"X-API-Key": API_KEY},
        ) as res:
            if res.status >= 400:
                raise RuntimeError(build_api_error_message("GET", path, res.status, await res.text()))
            return await res.json()


async def api_post(path: str, payload: Optional[Dict[str, Any]] = None) -> Any:
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{API_BASE}{path}",
            json=payload,
            headers={"Content-Type": "application/json", "X-API-Key": API_KEY},
        ) as res:
            if res.status >= 400:
                raise RuntimeError(build_api_error_message("POST", path, res.status, await res.text()))
            return await res.json()


async def api_delete(path: str) -> Any:
    async with aiohttp.ClientSession() as session:
        async with session.delete(
            f"{API_BASE}{path}",
            headers={"X-API-Key": API_KEY},
        ) as res:
            if res.status >= 400:
                raise RuntimeError(build_api_error_message("DELETE", path, res.status, await res.text()))
            return await res.json()

class ArcBriefBot(discord.Client):
    def __init__(self):
        super().__init__(intents=discord.Intents.default())
        self.tree = app_commands.CommandTree(self)
        self._config_cache: Dict[str, Any] = {}
        self._config_cached_at = 0.0
        self._config_lock = asyncio.Lock()

    async def setup_hook(self):
        await self.tree.sync()

    async def get_default_language(self) -> str:
        now = time.time()
        if self._config_cache and now - self._config_cached_at <= CONFIG_CACHE_TTL_SECONDS:
            lang = str(self._config_cache.get("report_language") or "").strip()
            return lang if lang in LANGUAGE_MAP.values() else "English (US)"

        async with self._config_lock:
            now = time.time()
            if self._config_cache and now - self._config_cached_at <= CONFIG_CACHE_TTL_SECONDS:
                lang = str(self._config_cache.get("report_language") or "").strip()
                return lang if lang in LANGUAGE_MAP.values() else "English (US)"
            try:
                cfg = await api_get("/config")
                if isinstance(cfg, dict):
                    self._config_cache = cfg
                    self._config_cached_at = now
                    lang = str(cfg.get("report_language") or "").strip()
                    if lang in LANGUAGE_MAP.values():
                        return lang
            except Exception:
                pass
        return "English (US)"


bot = ArcBriefBot()


async def resolve_output_language(lang: Optional[str]) -> str:
    if lang and lang in LANGUAGE_MAP:
        return LANGUAGE_MAP[lang]
    return await bot.get_default_language()


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
@app_commands.describe(topic="Topic ID or topic name")
async def latest_brief(interaction: discord.Interaction, topic: str):
    await interaction.response.defer(thinking=True)
    try:
        topics = await api_get("/topics")
        matched_topic, error_message = resolve_topic_reference(topic, topics)
        if error_message:
            await interaction.followup.send(error_message)
            return
        assert matched_topic is not None
        brief = await api_get(f"/briefs/{matched_topic['id']}/latest")
        brief["topic_name"] = matched_topic.get("name", brief.get("topic_name"))
        content = brief.get("content", "")
        if not content:
            await interaction.followup.send("No brief content.")
            return
        message = format_brief_mobile_message(brief)
        await interaction.followup.send(message)
    except Exception as e:
        await interaction.followup.send(f"Failed to get brief: {e}")


@bot.tree.command(name="research", description="Run a deep research query")
@app_commands.describe(query="Research question", lang="Output language (optional)")
@app_commands.choices(
    lang=[
        app_commands.Choice(name="English", value="en"),
        app_commands.Choice(name="中文", value="zh"),
        app_commands.Choice(name="日本語", value="ja"),
    ]
)
async def research(interaction: discord.Interaction, query: str, lang: Optional[app_commands.Choice[str]] = None):
    await interaction.response.defer(thinking=True)
    try:
        language = await resolve_output_language(lang.value if lang else None)
        run = await api_post("/run", {"query": query, "language": language})
        run_id = run.get("run_id")
        if not run_id:
            await interaction.followup.send("Failed to start run.")
            return

        await interaction.followup.send(f"Started research: `{run_id}` ({language}). Polling for completion...")

        report = ""
        last_status = "running"
        for _ in range(180):
            status = await api_get(f"/status/{run_id}")
            last_status = status.get("status") or last_status
            if status.get("report_content"):
                report = status.get("report_content", "")
            if last_status in {"done", "error"}:
                break
            await asyncio.sleep(2)

        if not report:
            await interaction.channel.send(
                format_long_task_status_message(kind="research", run_id=run_id, status=last_status)
            )
            return

        summary = format_research_mobile_message(
            run_id=run_id,
            query=query,
            language=language,
            report=report,
        )
        await interaction.channel.send(summary)

    except Exception as e:
        await interaction.followup.send(f"Research failed: {e}")


@bot.tree.command(name="ask", description="Ask a question about recent news briefs")
@app_commands.describe(
    question="Your question (e.g. 'What happened with OpenAI this week?')",
    topic="Optional topic filter: 'ai', 'policy', 'global', 'macro'",
    lang="Output language (optional)",
)
@app_commands.choices(
    lang=[
        app_commands.Choice(name="English", value="en"),
        app_commands.Choice(name="中文", value="zh"),
        app_commands.Choice(name="日本語", value="ja"),
    ]
)
async def ask(
    interaction: discord.Interaction,
    question: str,
    topic: Optional[str] = None,
    lang: Optional[app_commands.Choice[str]] = None,
):
    await interaction.response.defer(thinking=True)
    topic_id = None
    language = await resolve_output_language(lang.value if lang else None)
    if topic:
        try:
            topics = await api_get("/topics")
            matches = [t for t in topics if topic.lower() in t["name"].lower()]
            if matches:
                topic_id = matches[0]["id"]
        except Exception:
            pass  # topic filter is optional; proceed without it

    try:
        result = await api_post("/chat", {"message": question, "topic_id": topic_id, "language": language})
        response = format_ask_mobile_message(result)
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
        message = format_digest_mobile_message(list(seen.values()))
        await interaction.followup.send(message)
    except Exception as e:
        await interaction.followup.send(f"Error: {e}")


@bot.tree.command(name="tldr", description="Fetch a URL and return a mobile-friendly summary")
@app_commands.describe(url="Public article URL", lang="Output language (optional)")
@app_commands.choices(
    lang=[
        app_commands.Choice(name="English", value="en"),
        app_commands.Choice(name="中文", value="zh"),
        app_commands.Choice(name="日本語", value="ja"),
    ]
)
async def tldr(
    interaction: discord.Interaction,
    url: str,
    lang: Optional[app_commands.Choice[str]] = None,
):
    await interaction.response.defer(thinking=True)
    try:
        language = await resolve_output_language(lang.value if lang else None)
        result = await api_post(
            "/tldr",
            {
                "url": url,
                "language": language,
                "created_by": f"discord:{interaction.user.id}",
            },
        )
        await interaction.followup.send(format_tldr_mobile_message(result))
    except Exception as e:
        await interaction.followup.send(f"TL;DR failed: {e}")


@bot.tree.command(name="analyze", description="Run a PM-style product or company analysis")
@app_commands.describe(product="Product / company / initiative to analyze", lang="Output language (optional)")
@app_commands.choices(
    lang=[
        app_commands.Choice(name="English", value="en"),
        app_commands.Choice(name="中文", value="zh"),
        app_commands.Choice(name="日本語", value="ja"),
    ]
)
async def analyze(
    interaction: discord.Interaction,
    product: str,
    lang: Optional[app_commands.Choice[str]] = None,
):
    await interaction.response.defer(thinking=True)
    try:
        language = await resolve_output_language(lang.value if lang else None)
        run = await api_post("/analyze", {"product": product, "language": language})
        run_id = run.get("run_id")
        if not run_id:
            await interaction.followup.send("Failed to start analysis.")
            return

        await interaction.followup.send(f"Started analysis: `{run_id}` ({language}). Polling for completion...")

        report = ""
        last_status = "running"
        for _ in range(180):
            status = await api_get(f"/status/{run_id}")
            last_status = status.get("status") or last_status
            if status.get("report_content"):
                report = status.get("report_content", "")
            if last_status in {"done", "error"}:
                break
            await asyncio.sleep(2)

        if not report:
            await interaction.channel.send(
                format_long_task_status_message(kind="analyze", run_id=run_id, status=last_status)
            )
            return

        summary = format_analyze_mobile_message(
            run_id=run_id,
            subject=product,
            language=language,
            report=report,
        )
        await interaction.channel.send(summary)

    except Exception as e:
        await interaction.followup.send(f"Analyze failed: {e}")


@bot.tree.command(name="save", description="Save a brief for later review")
@app_commands.describe(brief_id="Brief ID to save", note="Optional note")
async def save_brief(
    interaction: discord.Interaction,
    brief_id: int,
    note: Optional[str] = None,
):
    await interaction.response.defer(thinking=True)
    try:
        result = await api_post(
            "/bookmarks",
            {
                "user_id": f"discord:{interaction.user.id}",
                "brief_id": brief_id,
                "note": note,
            },
        )
        await interaction.followup.send(
            format_bookmark_action_message(result.get("status", "saved"), brief_id=brief_id, note=note)
        )
    except Exception as e:
        await interaction.followup.send(f"Save failed: {e}")


@bot.tree.command(name="saved", description="List your saved briefs")
async def saved_briefs(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)
    try:
        result = await api_get(f"/bookmarks/discord:{interaction.user.id}")
        await interaction.followup.send(format_saved_mobile_message(result.get("items", [])))
    except Exception as e:
        await interaction.followup.send(f"Load saved briefs failed: {e}")


@bot.tree.command(name="unsave", description="Remove a saved brief")
@app_commands.describe(brief_id="Brief ID to remove from saved items")
async def unsave_brief(interaction: discord.Interaction, brief_id: int):
    await interaction.response.defer(thinking=True)
    try:
        result = await api_delete(f"/bookmarks/discord:{interaction.user.id}/{brief_id}")
        await interaction.followup.send(
            format_bookmark_action_message(result.get("status", "deleted"), brief_id=brief_id)
        )
    except Exception as e:
        await interaction.followup.send(f"Unsave failed: {e}")


def main():
    if not DISCORD_TOKEN:
        raise RuntimeError("DISCORD_TOKEN not set")
    bot.run(DISCORD_TOKEN)


if __name__ == "__main__":
    main()
