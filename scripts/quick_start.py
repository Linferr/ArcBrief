#!/usr/bin/env python3
"""
ArcBrief 快速启动脚本

一键完成：
1. 创建预置主题（AI简讯）
2. 执行首次采集
3. 生成首份简讯
4. 显示结果

用法：
    python scripts/quick_start.py           # 默认创建AI主题
    python scripts/quick_start.py --preset tech  # 创建科技主题
    python scripts/quick_start.py --all     # 创建所有预置主题
"""

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from backend.db import ArcBriefDB
from backend.collection import Collector, collect_for_topic
from backend.briefing import build_brief_for_topic
from datetime import datetime

# 预置配置（与manage_topics.py保持同步）
PRESETS = {
    "ai": {
        "name": "AI每日简讯",
        "keywords": ["AI", "GPT", "LLM", "大模型", "机器学习", "深度学习", "Claude", "OpenAI"],
        "rss_sources": [
            "https://hnrss.org/frontpage",
            "https://huggingface.co/blog/feed.xml",
        ],
        "scrape_frequency_hours": 4,
        "push_time": "08:00",
    },
    "tech": {
        "name": "科技资讯",
        "keywords": ["科技", "互联网", "创业", "融资", "苹果", "谷歌"],
        "rss_sources": [
            "https://hnrss.org/frontpage",
            "https://feeds.feedburner.com/TechCrunch/",
        ],
        "scrape_frequency_hours": 4,
        "push_time": "08:30",
    },
    "sec": {
        "name": "安全资讯",
        "keywords": ["安全", "漏洞", "CVE", "黑客", "勒索"],
        "rss_sources": [
            "https://feeds.feedburner.com/TheHackersNews",
            "https://www.bleepingcomputer.com/feed/",
        ],
        "scrape_frequency_hours": 2,
        "push_time": "09:00",
    },
}


def run_quick_start(preset_name: str, db: ArcBriefDB, collector: Collector):
    """运行快速启动流程"""
    preset = PRESETS.get(preset_name)
    if not preset:
        print(f"❌ 未知预置: {preset_name}")
        return False

    print(f"\n{'='*50}")
    print(f"创建主题: {preset['name']}")
    print('='*50)

    # 1. 创建主题
    print("\n[1/3] 创建主题...")
    topic_id = db.create_topic(preset)
    topic = db.get_topic(topic_id)
    print(f"  ✅ 主题ID: {topic_id}")
    print(f"  ✅ 名称: {topic.name}")
    print(f"  ✅ 关键词: {', '.join(topic.keywords[:5])}...")
    print(f"  ✅ RSS源: {len(topic.rss_sources)} 个")

    # 2. 采集内容
    print("\n[2/3] 采集内容...")
    items = collect_for_topic(topic, collector, max_tavily_results=5)
    saved = db.save_articles(topic_id, items)
    print(f"  ✅ 采集到: {len(items)} 篇")
    print(f"  ✅ 保存: {saved} 篇")

    if not items:
        print("  ⚠️  未采集到内容，可能是网络问题")
        return True

    # 3. 生成简讯
    print("\n[3/3] 生成简讯...")
    brief = build_brief_for_topic(topic, items)
    date_str = datetime.now().strftime("%Y-%m-%d")
    db.save_brief(topic_id, date_str, brief, len(items))
    print(f"  ✅ 简讯已生成 ({len(brief)} 字符)")

    # 显示简讯预览
    print("\n" + "-"*50)
    print("简讯预览:")
    print("-"*50)
    print(brief[:800])
    if len(brief) > 800:
        print(f"\n... (共 {len(brief)} 字符)")
    print("-"*50)

    return True


def main():
    parser = argparse.ArgumentParser(description="ArcBrief 快速启动")
    parser.add_argument("--preset", choices=list(PRESETS.keys()), default="ai",
                        help="使用的预置配置")
    parser.add_argument("--all", action="store_true", help="创建所有预置主题")
    parser.add_argument("--db", default="arcbrief.db", help="数据库路径")
    args = parser.parse_args()

    os.chdir(ROOT)

    print("\n" + "="*50)
    print("ArcBrief 快速启动")
    print("="*50)

    db = ArcBriefDB(args.db)
    collector = Collector()

    if args.all:
        for preset_name in PRESETS:
            run_quick_start(preset_name, db, collector)
    else:
        run_quick_start(args.preset, db, collector)

    # 打印后续步骤
    print("\n" + "="*50)
    print("下一步")
    print("="*50)
    print("""
1. 启动后端服务:
   uvicorn backend.main:app --reload --port 8000

2. 启动前端 (可选):
   cd frontend && npm run dev

3. 启动Discord Bot (可选):
   python discord_bot.py

4. 管理主题:
   python scripts/manage_topics.py list
   python scripts/manage_topics.py show 1

5. 手动触发采集/简讯:
   curl -X POST http://localhost:8000/api/topics/1/collect
   curl -X POST http://localhost:8000/api/topics/1/brief

6. 获取最新简讯:
   curl http://localhost:8000/api/briefs/1/latest
""")


if __name__ == "__main__":
    main()
