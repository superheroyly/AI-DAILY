"""
AI 日报 - 每日 AI 前沿速递
自动抓取 AI Valley 新闻 → DeepSeek 翻译整理 → 语音合成 → 发布 Apple Podcasts

用法:
    python main.py                  # 自动抓取当天文章
    python main.py --date "Mar 26, 2026"  # 抓取指定日期文章
    python main.py --list-voices    # 列出可用的中文语音
"""

import sys
import asyncio
import logging
import argparse
from pathlib import Path

import yaml

from src.pipeline import Pipeline
from src.tts import TTSEngine


def setup_logging():
    """配置日志输出"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(
                "ai-daily-podcast.log",
                encoding="utf-8",
                mode="a",
            ),
        ],
    )


def load_config() -> dict:
    """加载配置文件"""
    config_path = Path(__file__).parent / "config" / "settings.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"配置文件不存在: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


async def list_voices():
    """列出可用的中文语音"""
    config = load_config()
    tts = TTSEngine(config)
    voices = await tts.list_voices("zh")
    print("\n🎤 可用的中文语音列表:\n")
    print(f"{'名称':<35} {'性别':<8} {'地区':<10}")
    print("-" * 55)
    for v in voices:
        print(f"{v['ShortName']:<35} {v['Gender']:<8} {v['Locale']:<10}")
    print(f"\n共 {len(voices)} 个语音")


async def main():
    """主入口"""
    parser = argparse.ArgumentParser(
        description="AI 日报 - 每日 AI 前沿速递播客生成器"
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help='指定抓取日期，格式: "Mar 26, 2026"',
    )
    parser.add_argument(
        "--list-voices",
        action="store_true",
        help="列出可用的中文 TTS 语音",
    )

    args = parser.parse_args()

    # 列出语音
    if args.list_voices:
        await list_voices()
        return

    # 正常流程
    setup_logging()
    logger = logging.getLogger(__name__)

    try:
        config = load_config()
        pipeline = Pipeline(config)
        success = await pipeline.run(target_date=args.date)

        if success:
            logger.info("✅ 流水线执行成功")
            sys.exit(0)
        else:
            logger.info("ℹ️ 今日无新内容需要处理")
            sys.exit(0)

    except Exception as e:
        logger.error(f"💥 流水线执行失败: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
