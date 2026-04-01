"""
translator.py - DeepSeek 翻译 + 新闻简报整理模块
将英文 AI 新闻翻译为中文，并整理成适合播报的新闻简报脚本
"""

import os
import time
import logging
from datetime import datetime, timezone, timedelta

from openai import OpenAI

logger = logging.getLogger(__name__)

CST = timezone(timedelta(hours=8))

# 新闻简报 Prompt
BRIEFING_PROMPT = """你是一位专业的 AI 行业新闻播报员，名叫"小 AI"。请将以下英文 AI 新闻整理成一份中文新闻简报脚本。

## 风格要求
- **新闻简报风格**，就像每日早间科技新闻播报
- 语言简洁、通俗易懂，避免过于学术化或晦涩的表达
- **适合语音朗读**，使用自然口语化表达，避免出现缩写、URL 链接或特殊符号
- 专业术语首次出现时简要解释
- 适当加入一些生动的比喻或类比帮助理解

## 结构要求
1. **开场白**：以"大家好，欢迎收听 AI 日报，今天是{date}。我是你们的 AI 新闻播报员小 AI。今天的 AI 世界又有哪些新动态呢？让我们一起来看看。"开头
2. **核心新闻**：每条新闻独立成段，包含：
   - 简短有力的引题（如"首先来看今天的头条"、"接下来是第二条"）
   - 新闻要点（是什么、为什么重要、有什么影响）
   - 简短点评或展望
3. **工具和资源推荐**：如有 AI 工具推荐，简要提及 2-3 个最有价值的
4. **行业动态**：如有融资或合作消息，简要提及
5. **结尾**：以"好的，以上就是今天的 AI 日报全部内容。如果你觉得有收获，欢迎订阅我们的播客。我们明天再见！"结尾

## 重要约束
- 总字数控制在 **1500 到 2500 字** 之间（约 5-8 分钟朗读量）
- **不要**包含任何 URL 链接、邮箱地址
- **不要**包含 emoji 表情符号
- **不要**包含 markdown 格式标记
- 所有英文品牌名/产品名保持英文原名，但加简短中文说明
- 数字使用阿拉伯数字
- 在每个段落结尾处标注 [pause] 用于后续 TTS 添加停顿

## 今日日期
{date}

## 原始新闻内容
{content}
"""


class Translator:
    """DeepSeek 翻译 + 新闻简报整理器"""

    def __init__(self, config: dict):
        api_key = os.environ.get("DEEPSEEK_API_KEY")
        if not api_key:
            raise ValueError("环境变量 DEEPSEEK_API_KEY 未设置")

        self.client = OpenAI(
            api_key=api_key,
            base_url=config["deepseek"]["base_url"],
        )
        self.model = config["deepseek"]["model"]
        self.temperature = config["deepseek"]["temperature"]
        self.max_tokens = config["deepseek"]["max_tokens"]

    def _format_date_chinese(self) -> str:
        """获取中文格式的今日日期"""
        now = datetime.now(CST)
        weekday_map = ["一", "二", "三", "四", "五", "六", "日"]
        weekday = weekday_map[now.weekday()]
        return f"{now.year}年{now.month}月{now.day}日，星期{weekday}"

    def _merge_articles_content(self, articles: list) -> str:
        """将多篇文章合并为一份待翻译的文本"""
        parts = []
        for i, article in enumerate(articles, 1):
            parts.append(f"=== Article {i} ===")
            parts.append(f"Title: {article.title}")
            if article.subtitle:
                parts.append(f"Subtitle: {article.subtitle}")
            parts.append(f"Date: {article.date}")
            parts.append(f"Content:\n{article.raw_content}")
            parts.append("")

        return "\n".join(parts)

    def translate_and_brief(self, articles: list, date_override: str | None = None) -> str:
        """
        将文章列表翻译并整理成中文新闻简报脚本。
        
        Args:
            articles: Article 对象列表
            date_override: 可选日期覆盖
            
        Returns:
            中文新闻简报脚本文本
        """
        if not articles:
            logger.warning("⚠️ 没有文章需要翻译")
            return ""

        date_str = date_override or self._format_date_chinese()
        merged_content = self._merge_articles_content(articles)

        prompt = BRIEFING_PROMPT.format(
            date=date_str,
            content=merged_content,
        )

        logger.info(f"🤖 正在调用 DeepSeek API 翻译并整理新闻简报...")
        logger.info(f"   模型: {self.model}, 温度: {self.temperature}")
        logger.info(f"   输入内容长度: {len(merged_content)} 字符")

        # 带重试的 API 调用
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {
                            "role": "system",
                            "content": "你是一位专业的中文科技新闻播报员，擅长将英文 AI 行业新闻翻译并整理成通俗易懂的中文播报稿。",
                        },
                        {
                            "role": "user",
                            "content": prompt,
                        },
                    ],
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                )

                result = response.choices[0].message.content
                usage = response.usage

                logger.info(f"✅ DeepSeek API 调用成功")
                logger.info(f"   输入 tokens: {usage.prompt_tokens}")
                logger.info(f"   输出 tokens: {usage.completion_tokens}")
                logger.info(f"   生成简报长度: {len(result)} 字符")

                return result.strip()

            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = 2 ** (attempt + 1)
                    logger.warning(f"⚠️ DeepSeek API 调用失败 (尝试 {attempt + 1}/{max_retries}): {e}，{wait_time}秒后重试")
                    time.sleep(wait_time)
                else:
                    logger.error(f"❌ DeepSeek API 调用失败: {e}")
                    raise
