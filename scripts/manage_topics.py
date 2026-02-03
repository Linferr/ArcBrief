#!/usr/bin/env python3
"""
ArcBrief 主题管理工具

用法：
    python scripts/manage_topics.py list                    # 列出所有主题
    python scripts/manage_topics.py create --preset ai      # 创建预置AI主题
    python scripts/manage_topics.py create --preset tech    # 创建预置科技主题
    python scripts/manage_topics.py create --preset sec     # 创建预置安全主题
    python scripts/manage_topics.py update 1 --freq 2       # 更新采集频率为2小时
    python scripts/manage_topics.py update 1 --time 09:00   # 更新推送时间
    python scripts/manage_topics.py add-rss 1 "https://..."  # 添加RSS源
    python scripts/manage_topics.py delete 1                # 删除主题
    python scripts/manage_topics.py test-rss "https://..."  # 测试RSS源
"""

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from backend.db import ArcBriefDB
from backend.collection import Collector

# ============================================
# 预置主题配置
# ============================================

PRESETS = {
    "ai": {
        "name": "AI每日简讯",
        "keywords": ["AI", "GPT", "LLM", "大模型", "机器学习", "深度学习", "Claude", "OpenAI", "Anthropic"],
        "rss_sources": [
            "https://hnrss.org/frontpage",                      # Hacker News
            "https://www.reddit.com/r/MachineLearning/.rss",    # Reddit ML
            "https://huggingface.co/blog/feed.xml",             # HuggingFace Blog
            "https://openai.com/blog/rss.xml",                  # OpenAI Blog
            "https://www.deeplearning.ai/blog/feed/",           # DeepLearning.AI
        ],
        "scrape_frequency_hours": 4,
        "push_time": "08:00",
    },
    "tech": {
        "name": "科技资讯",
        "keywords": ["科技", "互联网", "创业", "融资", "苹果", "谷歌", "微软", "芯片"],
        "rss_sources": [
            "https://hnrss.org/frontpage",
            "https://36kr.com/feed",                            # 36氪
            "https://www.geekpark.net/rss",                     # 极客公园
            "https://feeds.feedburner.com/TechCrunch/",         # TechCrunch
            "https://www.theverge.com/rss/index.xml",           # The Verge
        ],
        "scrape_frequency_hours": 4,
        "push_time": "08:30",
    },
    "sec": {
        "name": "安全资讯",
        "keywords": ["安全", "漏洞", "CVE", "黑客", "勒索", "APT", "恶意软件"],
        "rss_sources": [
            "https://feeds.feedburner.com/TheHackersNews",      # The Hacker News
            "https://www.bleepingcomputer.com/feed/",           # BleepingComputer
            "https://krebsonsecurity.com/feed/",                # Krebs on Security
            "https://www.darkreading.com/rss.xml",              # Dark Reading
            "https://threatpost.com/feed/",                     # Threatpost
        ],
        "scrape_frequency_hours": 2,  # 安全资讯更频繁
        "push_time": "09:00",
    },
    "dev": {
        "name": "开发者周刊",
        "keywords": ["Python", "JavaScript", "Rust", "Go", "开源", "GitHub", "框架"],
        "rss_sources": [
            "https://hnrss.org/frontpage",
            "https://dev.to/feed",                              # Dev.to
            "https://css-tricks.com/feed/",                     # CSS-Tricks
            "https://blog.golang.org/feed.atom",                # Go Blog
            "https://blog.rust-lang.org/feed.xml",              # Rust Blog
        ],
        "scrape_frequency_hours": 6,
        "push_time": "10:00",
    },
}


def cmd_list(db: ArcBriefDB):
    """列出所有主题"""
    topics = db.list_topics()
    if not topics:
        print("暂无主题。使用 'create --preset ai' 创建一个。")
        return

    print(f"\n{'ID':<4} {'名称':<20} {'关键词':<30} {'频率':<6} {'推送':<8} {'状态'}")
    print("-" * 90)

    for t in topics:
        keywords = ", ".join(t.keywords[:3])
        if len(t.keywords) > 3:
            keywords += f"... (+{len(t.keywords)-3})"
        status = "✅ 启用" if t.is_active else "❌ 禁用"
        print(f"{t.id:<4} {t.name:<20} {keywords:<30} {t.scrape_frequency_hours}h{'':<4} {t.push_time:<8} {status}")

    print(f"\n共 {len(topics)} 个主题")


def cmd_create(db: ArcBriefDB, preset: str = None, name: str = None,
               keywords: list = None, rss: list = None,
               freq: int = 4, push_time: str = "08:00"):
    """创建主题"""
    if preset:
        if preset not in PRESETS:
            print(f"❌ 未知预置: {preset}")
            print(f"可用预置: {', '.join(PRESETS.keys())}")
            return
        config = PRESETS[preset].copy()
        print(f"使用预置配置: {preset}")
    else:
        if not name:
            print("❌ 需要指定 --name 或 --preset")
            return
        config = {
            "name": name,
            "keywords": keywords or [],
            "rss_sources": rss or [],
            "scrape_frequency_hours": freq,
            "push_time": push_time,
        }

    topic_id = db.create_topic(config)
    topic = db.get_topic(topic_id)

    print(f"\n✅ 主题创建成功!")
    print(f"  ID: {topic_id}")
    print(f"  名称: {topic.name}")
    print(f"  关键词: {', '.join(topic.keywords)}")
    print(f"  RSS源: {len(topic.rss_sources)} 个")
    print(f"  采集频率: 每 {topic.scrape_frequency_hours} 小时")
    print(f"  推送时间: {topic.push_time}")


def cmd_update(db: ArcBriefDB, topic_id: int, freq: int = None,
               push_time: str = None, active: bool = None):
    """更新主题配置"""
    topic = db.get_topic(topic_id)
    if not topic:
        print(f"❌ 主题 {topic_id} 不存在")
        return

    # 构建更新SQL
    updates = []
    params = []

    if freq is not None:
        updates.append("scrape_frequency_hours = ?")
        params.append(freq)

    if push_time is not None:
        updates.append("push_time = ?")
        params.append(push_time)

    if active is not None:
        updates.append("is_active = ?")
        params.append(1 if active else 0)

    if not updates:
        print("❌ 未指定更新内容")
        return

    import sqlite3
    conn = sqlite3.connect(db.db_path)
    sql = f"UPDATE topics SET {', '.join(updates)} WHERE id = ?"
    params.append(topic_id)
    conn.execute(sql, params)
    conn.commit()
    conn.close()

    print(f"✅ 主题 {topic_id} 更新成功")
    if freq is not None:
        print(f"  采集频率: 每 {freq} 小时")
    if push_time is not None:
        print(f"  推送时间: {push_time}")
    if active is not None:
        print(f"  状态: {'启用' if active else '禁用'}")


def cmd_add_rss(db: ArcBriefDB, topic_id: int, rss_url: str):
    """添加RSS源"""
    topic = db.get_topic(topic_id)
    if not topic:
        print(f"❌ 主题 {topic_id} 不存在")
        return

    if rss_url in topic.rss_sources:
        print(f"⚠️  RSS源已存在: {rss_url}")
        return

    import json
    import sqlite3

    new_sources = topic.rss_sources + [rss_url]
    conn = sqlite3.connect(db.db_path)
    conn.execute(
        "UPDATE topics SET rss_sources = ? WHERE id = ?",
        (json.dumps(new_sources, ensure_ascii=False), topic_id)
    )
    conn.commit()
    conn.close()

    print(f"✅ 已添加RSS源到主题 {topic_id}")
    print(f"  URL: {rss_url}")
    print(f"  总RSS源: {len(new_sources)} 个")


def cmd_add_keyword(db: ArcBriefDB, topic_id: int, keyword: str):
    """添加关键词"""
    topic = db.get_topic(topic_id)
    if not topic:
        print(f"❌ 主题 {topic_id} 不存在")
        return

    if keyword in topic.keywords:
        print(f"⚠️  关键词已存在: {keyword}")
        return

    import json
    import sqlite3

    new_keywords = topic.keywords + [keyword]
    conn = sqlite3.connect(db.db_path)
    conn.execute(
        "UPDATE topics SET keywords = ? WHERE id = ?",
        (json.dumps(new_keywords, ensure_ascii=False), topic_id)
    )
    conn.commit()
    conn.close()

    print(f"✅ 已添加关键词到主题 {topic_id}")
    print(f"  关键词: {keyword}")
    print(f"  总关键词: {len(new_keywords)} 个")


def cmd_delete(db: ArcBriefDB, topic_id: int, force: bool = False):
    """删除主题"""
    topic = db.get_topic(topic_id)
    if not topic:
        print(f"❌ 主题 {topic_id} 不存在")
        return

    if not force:
        confirm = input(f"确定删除主题 '{topic.name}' (ID={topic_id})? [y/N] ")
        if confirm.lower() != 'y':
            print("取消删除")
            return

    import sqlite3
    conn = sqlite3.connect(db.db_path)
    conn.execute("DELETE FROM briefs WHERE topic_id = ?", (topic_id,))
    conn.execute("DELETE FROM articles WHERE topic_id = ?", (topic_id,))
    conn.execute("DELETE FROM topics WHERE id = ?", (topic_id,))
    conn.commit()
    conn.close()

    print(f"✅ 已删除主题 '{topic.name}' 及相关数据")


def cmd_test_rss(rss_url: str):
    """测试RSS源"""
    print(f"测试RSS源: {rss_url}")

    collector = Collector()
    try:
        items = collector.fetch_rss(rss_url)
        print(f"\n✅ 获取成功! 共 {len(items)} 条")

        if items:
            print("\n最新5条:")
            for i, item in enumerate(items[:5], 1):
                title = item.title[:60] if item.title else "(无标题)"
                print(f"  {i}. {title}")
                if item.published_at:
                    print(f"     发布于: {item.published_at}")

    except Exception as e:
        print(f"\n❌ 获取失败: {e}")


def cmd_show(db: ArcBriefDB, topic_id: int):
    """显示主题详情"""
    topic = db.get_topic(topic_id)
    if not topic:
        print(f"❌ 主题 {topic_id} 不存在")
        return

    print(f"\n主题详情 (ID={topic_id})")
    print("=" * 50)
    print(f"名称: {topic.name}")
    print(f"状态: {'✅ 启用' if topic.is_active else '❌ 禁用'}")
    print(f"采集频率: 每 {topic.scrape_frequency_hours} 小时")
    print(f"推送时间: {topic.push_time}")
    print(f"推送渠道: {', '.join(topic.push_channels)}")

    print(f"\n关键词 ({len(topic.keywords)}):")
    for kw in topic.keywords:
        print(f"  - {kw}")

    print(f"\nRSS源 ({len(topic.rss_sources)}):")
    for rss in topic.rss_sources:
        print(f"  - {rss}")

    # 统计信息
    articles = db.get_recent_articles(topic_id, hours=24)
    brief = db.get_latest_brief(topic_id)

    print(f"\n统计:")
    print(f"  24h内文章: {len(articles)} 篇")
    print(f"  最新简讯: {brief.get('date', '无') if brief else '无'}")


def main():
    parser = argparse.ArgumentParser(description="ArcBrief 主题管理")
    parser.add_argument("--db", default="arcbrief.db", help="数据库路径")

    subparsers = parser.add_subparsers(dest="command", help="命令")

    # list
    subparsers.add_parser("list", help="列出所有主题")

    # create
    p_create = subparsers.add_parser("create", help="创建主题")
    p_create.add_argument("--preset", choices=list(PRESETS.keys()), help="使用预置配置")
    p_create.add_argument("--name", help="主题名称")
    p_create.add_argument("--keywords", nargs="+", help="关键词列表")
    p_create.add_argument("--rss", nargs="+", help="RSS源列表")
    p_create.add_argument("--freq", type=int, default=4, help="采集频率(小时)")
    p_create.add_argument("--time", default="08:00", help="推送时间 HH:MM")

    # update
    p_update = subparsers.add_parser("update", help="更新主题")
    p_update.add_argument("topic_id", type=int, help="主题ID")
    p_update.add_argument("--freq", type=int, help="采集频率(小时)")
    p_update.add_argument("--time", help="推送时间 HH:MM")
    p_update.add_argument("--enable", action="store_true", help="启用主题")
    p_update.add_argument("--disable", action="store_true", help="禁用主题")

    # add-rss
    p_add_rss = subparsers.add_parser("add-rss", help="添加RSS源")
    p_add_rss.add_argument("topic_id", type=int, help="主题ID")
    p_add_rss.add_argument("url", help="RSS URL")

    # add-keyword
    p_add_kw = subparsers.add_parser("add-keyword", help="添加关键词")
    p_add_kw.add_argument("topic_id", type=int, help="主题ID")
    p_add_kw.add_argument("keyword", help="关键词")

    # delete
    p_delete = subparsers.add_parser("delete", help="删除主题")
    p_delete.add_argument("topic_id", type=int, help="主题ID")
    p_delete.add_argument("--force", action="store_true", help="强制删除")

    # show
    p_show = subparsers.add_parser("show", help="显示主题详情")
    p_show.add_argument("topic_id", type=int, help="主题ID")

    # test-rss
    p_test = subparsers.add_parser("test-rss", help="测试RSS源")
    p_test.add_argument("url", help="RSS URL")

    args = parser.parse_args()

    # 切换到项目根目录
    os.chdir(ROOT)

    if args.command == "test-rss":
        cmd_test_rss(args.url)
        return

    db = ArcBriefDB(args.db)

    if args.command == "list" or args.command is None:
        cmd_list(db)
    elif args.command == "create":
        cmd_create(db, preset=args.preset, name=args.name,
                   keywords=args.keywords, rss=args.rss,
                   freq=args.freq, push_time=args.time)
    elif args.command == "update":
        active = None
        if args.enable:
            active = True
        elif args.disable:
            active = False
        cmd_update(db, args.topic_id, freq=args.freq,
                   push_time=args.time, active=active)
    elif args.command == "add-rss":
        cmd_add_rss(db, args.topic_id, args.url)
    elif args.command == "add-keyword":
        cmd_add_keyword(db, args.topic_id, args.keyword)
    elif args.command == "delete":
        cmd_delete(db, args.topic_id, force=args.force)
    elif args.command == "show":
        cmd_show(db, args.topic_id)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
