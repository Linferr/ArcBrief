#!/usr/bin/env python3
"""
ArcBrief 端到端测试脚本

测试流程：创建主题 → 采集 → 生成简讯 → (可选)Discord推送

用法：
    python scripts/e2e_test.py              # 完整测试
    python scripts/e2e_test.py --no-discord # 跳过Discord推送
    python scripts/e2e_test.py --cleanup    # 测试后清理测试数据
"""

import argparse
import asyncio
import os
import sys
import time
from pathlib import Path

# 添加项目根目录到路径
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from backend.db import ArcBriefDB
from backend.collection import Collector, collect_for_topic
from backend.briefing import build_brief_for_topic

# 测试用RSS源（可靠的科技/AI新闻源）
TEST_RSS_SOURCES = [
    "https://hnrss.org/frontpage",  # Hacker News
    "https://feeds.feedburner.com/TheHackersNews",  # The Hacker News Security
]

# 测试用关键词
TEST_KEYWORDS = ["AI", "GPT", "LLM", "机器学习", "Python"]


def print_step(step: str, msg: str):
    """打印步骤信息"""
    print(f"\n{'='*60}")
    print(f"[{step}] {msg}")
    print('='*60)


def print_result(success: bool, msg: str):
    """打印结果"""
    status = "✅ PASS" if success else "❌ FAIL"
    print(f"{status}: {msg}")


class E2ETest:
    def __init__(self, db_path: str = "arcbrief.db"):
        self.db = ArcBriefDB(db_path)
        self.collector = Collector()
        self.test_topic_id = None
        self.results = []

    def run_all(self, skip_discord: bool = False, cleanup: bool = False):
        """运行所有测试"""
        print("\n" + "="*60)
        print("ArcBrief 端到端测试")
        print("="*60)

        try:
            # Step 1: 创建测试主题
            self.test_create_topic()

            # Step 2: 采集内容
            self.test_collection()

            # Step 3: 生成简讯
            self.test_brief_generation()

            # Step 4: Discord推送（可选）
            if not skip_discord:
                self.test_discord_push()
            else:
                print_step("4", "跳过 Discord 推送测试")

            # 打印总结
            self.print_summary()

        finally:
            if cleanup:
                self.cleanup()

    def test_create_topic(self):
        """测试创建主题"""
        print_step("1", "创建测试主题")

        try:
            topic_data = {
                "name": "E2E测试主题",
                "keywords": TEST_KEYWORDS,
                "rss_sources": TEST_RSS_SOURCES,
                "scrape_frequency_hours": 1,  # 测试用1小时
                "push_time": "09:00",
                "push_channels": ["discord"],
            }

            self.test_topic_id = self.db.create_topic(topic_data)
            topic = self.db.get_topic(self.test_topic_id)

            assert topic is not None, "主题创建失败"
            assert topic.name == "E2E测试主题", "主题名称不匹配"
            assert len(topic.keywords) == len(TEST_KEYWORDS), "关键词数量不匹配"
            assert len(topic.rss_sources) == len(TEST_RSS_SOURCES), "RSS源数量不匹配"

            print(f"  主题ID: {self.test_topic_id}")
            print(f"  名称: {topic.name}")
            print(f"  关键词: {topic.keywords}")
            print(f"  RSS源: {len(topic.rss_sources)} 个")
            print(f"  采集频率: 每 {topic.scrape_frequency_hours} 小时")
            print(f"  推送时间: {topic.push_time}")

            print_result(True, "主题创建成功")
            self.results.append(("创建主题", True))

        except Exception as e:
            print_result(False, f"主题创建失败: {e}")
            self.results.append(("创建主题", False))
            raise

    def test_collection(self):
        """测试内容采集"""
        print_step("2", "采集内容")

        try:
            topic = self.db.get_topic(self.test_topic_id)
            assert topic is not None, "无法获取测试主题"

            print("  正在采集RSS源...")
            start_time = time.time()
            items = collect_for_topic(topic, self.collector, max_tavily_results=3)
            elapsed = time.time() - start_time

            print(f"  采集耗时: {elapsed:.2f}秒")
            print(f"  采集到 {len(items)} 篇文章")

            if items:
                # 打印前3篇
                print("\n  前3篇文章预览:")
                for i, item in enumerate(items[:3], 1):
                    title = item.get("title", "")[:50]
                    source = item.get("source", "unknown")
                    print(f"    {i}. [{source}] {title}...")

            # 保存到数据库
            saved = self.db.save_articles(self.test_topic_id, items)
            print(f"\n  保存到数据库: {saved} 篇")

            # 验证
            db_items = self.db.get_recent_articles(self.test_topic_id, hours=24)
            print(f"  数据库中文章数: {len(db_items)}")

            assert len(items) > 0, "未采集到任何文章"
            print_result(True, f"采集成功，共 {len(items)} 篇")
            self.results.append(("内容采集", True))

        except Exception as e:
            print_result(False, f"采集失败: {e}")
            self.results.append(("内容采集", False))
            raise

    def test_brief_generation(self):
        """测试简讯生成"""
        print_step("3", "生成简讯")

        try:
            topic = self.db.get_topic(self.test_topic_id)
            items = self.db.get_recent_articles(self.test_topic_id, hours=24)

            print(f"  使用 {len(items)} 篇文章生成简讯...")

            start_time = time.time()
            brief = build_brief_for_topic(topic, items)
            elapsed = time.time() - start_time

            print(f"  生成耗时: {elapsed:.2f}秒")
            print(f"  简讯长度: {len(brief)} 字符")

            # 保存简讯
            from datetime import datetime
            date_str = datetime.now().strftime("%Y-%m-%d")
            self.db.save_brief(self.test_topic_id, date_str, brief, len(items))

            # 验证
            saved_brief = self.db.get_latest_brief(self.test_topic_id)
            assert saved_brief is not None, "简讯保存失败"

            # 打印简讯预览
            print("\n  简讯预览 (前500字):")
            print("-" * 40)
            print(brief[:500])
            if len(brief) > 500:
                print("...")
            print("-" * 40)

            print_result(True, "简讯生成成功")
            self.results.append(("简讯生成", True))

            return brief

        except Exception as e:
            print_result(False, f"简讯生成失败: {e}")
            self.results.append(("简讯生成", False))
            raise

    def test_discord_push(self):
        """测试Discord推送"""
        print_step("4", "Discord推送测试")

        discord_token = os.getenv("DISCORD_TOKEN", "")
        test_channel_id = os.getenv("DISCORD_TEST_CHANNEL_ID", "")

        if not discord_token:
            print("  ⚠️  DISCORD_TOKEN 未设置，跳过推送测试")
            print("  提示: 在.env中设置 DISCORD_TOKEN 启用Discord推送")
            self.results.append(("Discord推送", None))  # None = 跳过
            return

        if not test_channel_id:
            print("  ⚠️  DISCORD_TEST_CHANNEL_ID 未设置，跳过推送测试")
            print("  提示: 在.env中设置测试频道ID")
            self.results.append(("Discord推送", None))
            return

        try:
            import discord
            from discord_bot import chunk_text

            brief = self.db.get_latest_brief(self.test_topic_id)
            if not brief:
                print_result(False, "无简讯可推送")
                self.results.append(("Discord推送", False))
                return

            content = brief.get("content", "")
            print(f"  准备推送简讯到频道 {test_channel_id}...")
            print(f"  简讯分为 {len(chunk_text(content))} 个片段")

            # 使用同步方式发送（测试用）
            async def send_test():
                intents = discord.Intents.default()
                client = discord.Client(intents=intents)

                @client.event
                async def on_ready():
                    try:
                        channel = client.get_channel(int(test_channel_id))
                        if channel:
                            await channel.send(f"**[E2E测试] {brief.get('date', '')} 简讯**")
                            for chunk in chunk_text(content):
                                await channel.send(f"```markdown\n{chunk}\n```")
                            print("  ✅ 推送成功")
                        else:
                            print(f"  ❌ 找不到频道 {test_channel_id}")
                    finally:
                        await client.close()

                await client.start(discord_token)

            asyncio.run(send_test())
            print_result(True, "Discord推送成功")
            self.results.append(("Discord推送", True))

        except Exception as e:
            print_result(False, f"Discord推送失败: {e}")
            self.results.append(("Discord推送", False))

    def print_summary(self):
        """打印测试总结"""
        print("\n" + "="*60)
        print("测试总结")
        print("="*60)

        passed = 0
        failed = 0
        skipped = 0

        for name, result in self.results:
            if result is True:
                status = "✅ PASS"
                passed += 1
            elif result is False:
                status = "❌ FAIL"
                failed += 1
            else:
                status = "⏭️  SKIP"
                skipped += 1
            print(f"  {status}: {name}")

        print("-" * 40)
        print(f"  通过: {passed}  失败: {failed}  跳过: {skipped}")

        if failed == 0:
            print("\n🎉 所有测试通过！")
        else:
            print(f"\n⚠️  有 {failed} 个测试失败")

    def cleanup(self):
        """清理测试数据"""
        print_step("清理", "删除测试数据")

        if self.test_topic_id:
            # 注意：这里简单起见直接用SQL删除，实际应该在db.py中添加删除方法
            import sqlite3
            conn = sqlite3.connect(self.db.db_path)
            try:
                conn.execute("DELETE FROM briefs WHERE topic_id = ?", (self.test_topic_id,))
                conn.execute("DELETE FROM articles WHERE topic_id = ?", (self.test_topic_id,))
                conn.execute("DELETE FROM topics WHERE id = ?", (self.test_topic_id,))
                conn.commit()
                print(f"  已删除测试主题 ID={self.test_topic_id} 及相关数据")
            finally:
                conn.close()


def main():
    parser = argparse.ArgumentParser(description="ArcBrief 端到端测试")
    parser.add_argument("--no-discord", action="store_true", help="跳过Discord推送测试")
    parser.add_argument("--cleanup", action="store_true", help="测试后清理测试数据")
    parser.add_argument("--db", default="arcbrief.db", help="数据库路径")
    args = parser.parse_args()

    # 切换到项目根目录
    os.chdir(ROOT)

    test = E2ETest(db_path=args.db)
    test.run_all(skip_discord=args.no_discord, cleanup=args.cleanup)


if __name__ == "__main__":
    main()
