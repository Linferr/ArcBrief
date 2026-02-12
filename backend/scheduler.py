"""APScheduler integration for collection + briefing + Discord push."""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from .collection import Collector, collect_for_topic
from .briefing import build_brief_for_topic

logger = logging.getLogger(__name__)


class DiscordPusher:
    """Discord消息推送器（可选功能）"""

    def __init__(self, token: Optional[str] = None, webhook_url: Optional[str] = None):
        self.token = token or os.getenv("DISCORD_TOKEN", "")
        self.webhook_url = webhook_url or os.getenv("DISCORD_WEBHOOK_URL", "")
        self._client = None

    @property
    def enabled(self) -> bool:
        return bool(self.token or self.webhook_url)

    def push_via_webhook(self, content: str, channel_id: str = None) -> bool:
        """通过Webhook推送（简单方式）"""
        if not self.webhook_url:
            return False

        try:
            import requests
            chunks = self._chunk_text(content)
            for chunk in chunks:
                requests.post(self.webhook_url, json={
                    "content": f"```markdown\n{chunk}\n```"
                }, timeout=10)
            return True
        except Exception as e:
            logger.error(f"Discord webhook push failed: {e}")
            return False

    async def push_via_bot(self, content: str, channel_id: str) -> bool:
        """通过Bot推送（需要channel_id）"""
        if not self.token or not channel_id:
            return False

        try:
            import discord
            intents = discord.Intents.default()
            client = discord.Client(intents=intents)
            pushed = False

            @client.event
            async def on_ready():
                nonlocal pushed
                try:
                    channel = client.get_channel(int(channel_id))
                    if channel:
                        chunks = self._chunk_text(content)
                        for chunk in chunks:
                            await channel.send(f"```markdown\n{chunk}\n```")
                        pushed = True
                        logger.info(f"Discord push to channel {channel_id} success")
                    else:
                        logger.warning(f"Discord channel {channel_id} not found")
                except Exception as e:
                    logger.error(f"Discord push error: {e}")
                finally:
                    await client.close()

            # 运行客户端（带超时）
            await asyncio.wait_for(client.start(self.token), timeout=30)
            return pushed

        except asyncio.TimeoutError:
            logger.error("Discord push timeout")
            return False
        except Exception as e:
            logger.error(f"Discord bot push failed: {e}")
            return False

    def push_sync(self, content: str, channel_id: str = None) -> bool:
        """同步推送（供scheduler调用）"""
        # 优先使用webhook
        if self.webhook_url:
            return self.push_via_webhook(content, channel_id)

        # 使用bot
        if self.token and channel_id:
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                result = loop.run_until_complete(self.push_via_bot(content, channel_id))
                loop.close()
                return result
            except Exception as e:
                logger.error(f"Discord sync push failed: {e}")
                return False

        return False

    def _chunk_text(self, text: str, size: int = 1800) -> list:
        return [text[i:i+size] for i in range(0, len(text), size)]


class ArcBriefScheduler:
    def __init__(self, db, tavily_api_key: Optional[str] = None,
                 discord_token: Optional[str] = None,
                 discord_webhook: Optional[str] = None) -> None:
        self.db = db
        self.collector = Collector(tavily_api_key=tavily_api_key)
        self.scheduler = BackgroundScheduler()
        self.discord = DiscordPusher(token=discord_token, webhook_url=discord_webhook)

    def start(self) -> None:
        self._load_jobs()
        self.scheduler.start()

    def stop(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    def _load_jobs(self) -> None:
        for topic in self.db.list_topics():
            if not topic.is_active:
                continue
            self._add_collection_job(topic)
            self._add_daily_brief_job(topic)
        # Daily cleanup: remove articles older than 30 days
        self.scheduler.add_job(
            self._cleanup_task,
            trigger=CronTrigger(hour=2, minute=0),
            id="cleanup_old_articles",
            replace_existing=True,
        )

    def _add_collection_job(self, topic) -> None:
        job_id = f"collect_{topic.id}"
        trigger = IntervalTrigger(hours=topic.scrape_frequency_hours)
        self.scheduler.add_job(
            self._collection_task,
            trigger=trigger,
            args=[topic.id],
            id=job_id,
            replace_existing=True,
            next_run_time=datetime.now(),
        )

    def _add_daily_brief_job(self, topic) -> None:
        job_id = f"brief_{topic.id}"
        hour, minute = (topic.push_time.split(":") + ["00"])[:2]
        trigger = CronTrigger(hour=int(hour), minute=int(minute))
        self.scheduler.add_job(
            self._brief_task,
            trigger=trigger,
            args=[topic.id],
            id=job_id,
            replace_existing=True,
        )

    def _collection_task(self, topic_id: int) -> None:
        topic = self.db.get_topic(topic_id)
        if not topic:
            return
        started = datetime.now().isoformat()
        try:
            result = collect_for_topic(topic, self.collector)
            items = result["items"]
            for h in result.get("rss_health", []):
                self.db.upsert_rss_health(topic.id, h["rss_url"], h["status"], h["items_fetched"], last_error=h.get("last_error"))
            saved = self.db.save_articles(topic.id, items)
            self.db.log_brief_run(topic.id, "collect", "ok", len(items), saved, started_at=started)
            logger.info(f"Collection for '{topic.name}': {len(items)} items, {saved} saved")
        except Exception as e:
            self.db.log_brief_run(topic.id, "collect", "failed", error_message=str(e), started_at=started)
            logger.error(f"Collection failed for '{topic.name}': {e}")

    def _brief_task(self, topic_id: int) -> None:
        topic = self.db.get_topic(topic_id)
        if not topic:
            return
        started = datetime.now().isoformat()
        brief_hours = int(os.getenv("ARCBRIEF_NEWS_MAX_AGE_HOURS", "48"))
        try:
            items = self.db.get_recent_articles(topic_id, hours=brief_hours)
            brief = build_brief_for_topic(topic, items)
            date_str = datetime.now().strftime("%Y-%m-%d")
            self.db.save_brief(topic_id, date_str, brief, len(items))
            self.db.log_brief_run(topic.id, "brief", "ok", items_collected=len(items), started_at=started)
            logger.info(f"Brief generated for topic {topic.name}: {len(items)} articles")
        except Exception as e:
            self.db.log_brief_run(topic.id, "brief", "failed", error_message=str(e), started_at=started)
            logger.error(f"Brief generation failed for '{topic.name}': {e}")

        # Discord推送
        if self.discord.enabled and "discord" in topic.push_channels:
            # 尝试获取频道ID（可以存储在topic或环境变量中）
            channel_id = os.getenv(f"DISCORD_CHANNEL_{topic_id}") or os.getenv("DISCORD_DEFAULT_CHANNEL")
            header = f"# {date_str} {topic.name}\n\n"
            success = self.discord.push_sync(header + brief, channel_id)
            if success:
                logger.info(f"Discord push success for topic {topic.name}")
            else:
                logger.warning(f"Discord push failed for topic {topic.name}")

    def _cleanup_task(self) -> None:
        try:
            deleted = self.db.cleanup_old_articles(days=30)
            if deleted > 0:
                logger.info(f"Cleanup: removed {deleted} articles older than 30 days")
        except Exception as e:
            logger.error(f"Cleanup failed: {e}")

    def refresh_jobs(self) -> None:
        self.scheduler.remove_all_jobs()
        self._load_jobs()
