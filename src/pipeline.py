"""
pipeline.py - 主流程编排模块
协调 scraper → translator → tts → rss_generator 的完整流水线
"""

import json
import asyncio
import logging
from pathlib import Path
from datetime import datetime, timezone, timedelta

from src.scraper import Scraper
from src.translator import Translator
from src.tts import TTSEngine
from src.rss_generator import RSSGenerator

logger = logging.getLogger(__name__)

CST = timezone(timedelta(hours=8))


class Pipeline:
    """AI 日报完整生成流水线"""

    def __init__(self, config: dict):
        self.config = config
        self.output_cfg = config["output"]
        self.scraper = Scraper(config)
        self.translator = Translator(config)
        self.tts = TTSEngine(config)
        self.rss = RSSGenerator(config)

        # 确保输出目录存在
        for dir_key in ["base_dir", "audio_dir", "feed_dir", "data_dir", "articles_dir"]:
            Path(self.output_cfg[dir_key]).mkdir(parents=True, exist_ok=True)

    def _parse_target_date(self, target_date: str | None) -> str:
        """
        将目标日期转换为 YYYY-MM-DD 格式。
        
        Args:
            target_date: 格式 "Mar 26, 2026"，None 则使用今天

        Returns:
            YYYY-MM-DD 格式日期字符串
        """
        if target_date:
            try:
                dt = datetime.strptime(target_date.strip(), "%b %d, %Y")
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                logger.warning(f"⚠️ 无法解析日期 '{target_date}'，使用今天")
        return datetime.now(CST).strftime("%Y-%m-%d")

    def _load_processed(self) -> set:
        """加载已处理文章的 URL 集合"""
        processed_file = self.output_cfg["processed_file"]
        if Path(processed_file).exists():
            with open(processed_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return set(data.get("urls", []))
        return set()

    def _save_processed(self, urls: set):
        """保存已处理文章的 URL 集合"""
        processed_file = self.output_cfg["processed_file"]
        Path(processed_file).parent.mkdir(parents=True, exist_ok=True)
        with open(processed_file, "w", encoding="utf-8") as f:
            json.dump({"urls": list(urls)}, f, ensure_ascii=False, indent=2)

    def _save_article_data(self, date: str, articles: list, briefing: str):
        """保存文章数据和简报到 JSON"""
        data = {
            "date": date,
            "generated_at": datetime.now(CST).isoformat(),
            "articles": [
                {
                    "title": a.title,
                    "subtitle": a.subtitle,
                    "url": a.url,
                    "date": a.date,
                    "content_length": len(a.raw_content),
                }
                for a in articles
            ],
            "briefing": briefing,
            "briefing_length": len(briefing),
        }

        filepath = Path(self.output_cfg["articles_dir"]) / f"{date}.json"
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info(f"💾 文章数据已保存: {filepath}")

    async def run(self, target_date: str | None = None) -> bool:
        """
        执行完整的生成流水线。
        
        Args:
            target_date: 可选，指定目标日期（格式 "Mar 26, 2026"）
                         用于测试或补充历史数据
                         
        Returns:
            True 表示成功生成新 episode，False 表示跳过
        """
        now = datetime.now(CST)

        # 使用目标日期或今天作为 episode 的日期标签
        episode_date = self._parse_target_date(target_date)

        logger.info("=" * 60)
        logger.info(f"🚀 AI 日报生成流水线启动")
        logger.info(f"   当前时间: {now.isoformat()}")
        logger.info(f"   目标日期: {episode_date}")
        logger.info("=" * 60)

        # ── Step 1: 抓取当日文章 ──
        logger.info("\n📰 Step 1/4: 抓取文章")
        articles = await self.scraper.scrape_today(target_date)

        if not articles:
            logger.warning(
                f"📭 {target_date or '今日'} 没有抓取到文章。"
                "可能原因: 周末/假期无更新、网站结构变更、网络问题。"
                "请检查 https://www.theaivalley.com/archive 是否有当日内容。"
            )
            return False

        # 检查是否已处理
        processed = self._load_processed()
        new_articles = [a for a in articles if a.url not in processed]

        if not new_articles:
            logger.info("✅ 所有文章已处理过，跳过")
            return False

        logger.info(f"📝 {len(new_articles)} 篇新文章待处理")

        # ── Step 2: 翻译 + 整理简报 ──
        logger.info("\n🤖 Step 2/4: 翻译整理新闻简报")
        briefing = self.translator.translate_and_brief(new_articles)

        if not briefing:
            logger.error("❌ 简报生成失败")
            return False

        # ── Step 3: 语音合成 ──
        logger.info("\n🎙️ Step 3/4: 语音合成")
        audio_filename = f"ai-daily-{episode_date}.mp3"
        audio_path = str(Path(self.output_cfg["audio_dir"]) / audio_filename)

        await self.tts.synthesize(briefing, audio_path)

        # ── Step 4: 生成/更新 RSS Feed ──
        logger.info("\n📡 Step 4/4: 生成 RSS Feed")
        # 取简报前 200 字作为 episode 描述
        description = briefing[:200].replace("\n", " ").strip()
        if len(briefing) > 200:
            description += "..."

        self.rss.generate_feed(
            date=episode_date,
            description=description,
            audio_path=audio_path,
        )

        # ── 保存记录 ──
        self._save_article_data(episode_date, new_articles, briefing)

        # 更新已处理列表
        for article in new_articles:
            processed.add(article.url)
        self._save_processed(processed)

        logger.info("\n" + "=" * 60)
        logger.info(f"🎉 AI 日报 {episode_date} 生成完成!")
        logger.info(f"   📄 文章数: {len(new_articles)}")
        logger.info(f"   📝 简报字数: {len(briefing)}")
        logger.info(f"   🎵 音频文件: {audio_path}")
        logger.info("=" * 60)

        return True
