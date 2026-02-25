"""APScheduler integration for collection + briefing + Discord push."""

from __future__ import annotations

import logging
import os
import re
import time
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from .constants import APP_CONFIG_DEFAULTS
from .collection import Collector, collect_for_topic
from .briefing import build_brief_for_topic

logger = logging.getLogger(__name__)


class DiscordPusher:
    """Discord Webhook 推送器（仅 webhook 模式，bot slash commands 见 discord_bot.py）"""

    def __init__(self, token: Optional[str] = None, webhook_url: Optional[str] = None):
        self.token = token or os.getenv("DISCORD_TOKEN", "")
        self.webhook_url = webhook_url or os.getenv("DISCORD_WEBHOOK_URL", "")

    @property
    def enabled(self) -> bool:
        return bool(self.webhook_url)

    def push_sync(self, content: str, webhook_url: str = None) -> bool:
        """推送到 Discord Webhook（3次重试，处理限速）"""
        url = webhook_url or self.webhook_url
        if not url:
            return False
        try:
            import requests
            all_sent = True
            for chunk in self._chunk_text(content):
                chunk_sent = False
                for attempt in range(3):
                    resp = requests.post(url, json={"content": chunk}, timeout=15)
                    if resp.status_code == 204:
                        chunk_sent = True
                        break
                    if resp.status_code == 429:
                        retry_after = 2.0
                        try:
                            retry_after = float((resp.json() or {}).get("retry_after", 2))
                        except Exception:
                            retry_after = 2.0
                        time.sleep(retry_after)
                        continue
                    logger.warning(f"Discord webhook got {resp.status_code}, attempt {attempt + 1}")
                    time.sleep(1.5 ** attempt)
                if not chunk_sent:
                    all_sent = False
                    logger.error("Discord webhook push failed for one chunk after retries.")
            return all_sent
        except Exception as e:
            logger.error(f"Discord webhook push failed: {e}")
            return False

    def _format_for_discord(self, text: str) -> str:
        """将 Markdown H1/H2/H3 转为 Discord 原生格式，移除多余水平线"""
        text = re.sub(r'^# (.+)$', r'**\1**', text, flags=re.MULTILINE)
        text = re.sub(r'^## (.+)$', r'__**\1**__', text, flags=re.MULTILINE)
        text = re.sub(r'^### (.+)$', r'**\1**', text, flags=re.MULTILINE)
        text = re.sub(r'^---+$', '', text, flags=re.MULTILINE)
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    def _chunk_text(self, text: str, size: int = 1900) -> list:
        """按换行边界切块，避免在句子中间截断"""
        chunks, current = [], ""
        for line in text.split("\n"):
            if len(current) + len(line) + 1 > size:
                if current:
                    chunks.append(current.rstrip())
                current = line + "\n"
            else:
                current += line + "\n"
        if current.strip():
            chunks.append(current.rstrip())
        return chunks or [text[:size]]


class ArcBriefScheduler:
    def __init__(self, db, tavily_api_key: Optional[str] = None,
                 discord_token: Optional[str] = None,
                 discord_webhook: Optional[str] = None) -> None:
        self.db = db
        self.collector = Collector(tavily_api_key=tavily_api_key)
        timezone_name = os.getenv("ARCBRIEF_SCHED_TZ", "UTC").strip() or "UTC"
        try:
            self.scheduler_tz = ZoneInfo(timezone_name)
        except Exception:
            logger.warning("Invalid ARCBRIEF_SCHED_TZ=%s; fallback to UTC", timezone_name)
            self.scheduler_tz = ZoneInfo("UTC")
        self.scheduler = BackgroundScheduler(timezone=self.scheduler_tz)
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
            trigger=CronTrigger(hour=2, minute=0, timezone=self.scheduler_tz),
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
        trigger = CronTrigger(hour=int(hour), minute=int(minute), timezone=self.scheduler_tz)
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
        brief = None
        date_str = datetime.now().strftime("%Y-%m-%d")
        try:
            items = self.db.get_recent_articles(topic_id, hours=brief_hours)
            config = self.db.get_app_config()
            merged_config = {**APP_CONFIG_DEFAULTS, **config}
            source_weights = self.db.get_source_reputations(topic_id)
            brief = build_brief_for_topic(
                topic,
                items,
                source_weights=source_weights,
                app_config=merged_config,
            )
            self.db.save_brief(topic_id, date_str, brief, len(items))
            self.db.log_brief_run(topic.id, "brief", "ok", items_collected=len(items), started_at=started)
            logger.info(f"Brief generated for topic {topic.name}: {len(items)} articles")
        except Exception as e:
            self.db.log_brief_run(topic.id, "brief", "failed", error_message=str(e), started_at=started)
            logger.error(f"Brief generation failed for '{topic.name}': {e}")

        # Discord推送（webhook 模式，支持 per-topic webhook 配置）
        topic_webhook = os.getenv(f"DISCORD_WEBHOOK_TOPIC_{topic_id}")
        target_webhook = topic_webhook or self.discord.webhook_url
        if brief and target_webhook and "discord" in topic.push_channels:
            header = f"**{date_str} | {topic.name}**\n\n"
            formatted = self.discord._format_for_discord(brief)
            success = self.discord.push_sync(header + formatted, webhook_url=target_webhook)
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
