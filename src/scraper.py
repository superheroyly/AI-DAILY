"""
scraper.py - 网页抓取模块
从 https://www.theaivalley.com/archive 抓取当日 AI 新闻文章
"""

import re
import logging
import asyncio
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# 中国标准时间 UTC+8
CST = timezone(timedelta(hours=8))


@dataclass
class Article:
    """抓取到的文章结构"""
    title: str
    subtitle: str
    date: str           # 原始日期字符串，如 "Mar 26, 2026"
    url: str
    raw_content: str    # 提取的正文纯文本
    sections: list = field(default_factory=list)


class Scraper:
    """AI Valley 网站抓取器"""

    def __init__(self, config: dict):
        self.archive_url = config["source"]["archive_url"]
        self.base_url = config["source"]["base_url"]
        self.user_agent = config["source"]["user_agent"]
        self.headers = {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }

    async def fetch_page(self, url: str, retries: int = 3) -> str:
        """获取网页 HTML 内容，带重试机制"""
        last_error = None
        for attempt in range(retries):
            try:
                async with httpx.AsyncClient(
                    headers=self.headers,
                    follow_redirects=True,
                    timeout=30.0
                ) as client:
                    resp = await client.get(url)
                    resp.raise_for_status()
                    return resp.text
            except (httpx.HTTPError, httpx.ConnectError) as e:
                last_error = e
                wait_time = 2 ** attempt
                logger.warning(f"  ⚠️ 请求失败 (尝试 {attempt + 1}/{retries}): {e}，{wait_time}秒后重试")
                await asyncio.sleep(wait_time)
        raise last_error

    def _parse_date(self, date_str: str) -> datetime | None:
        """解析日期字符串，如 'Mar 26, 2026'"""
        try:
            return datetime.strptime(date_str.strip(), "%b %d, %Y")
        except ValueError:
            return None

    def _get_today_str(self) -> str:
        """获取今天的日期字符串（CST），格式如 'Mar 30, 2026'"""
        now = datetime.now(CST)
        # 手动构造以避免 strftime 的前导零问题
        months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        return f"{months[now.month - 1]} {now.day}, {now.year}"

    def _extract_article_links(self, html: str, target_date: str | None = None) -> list[dict]:
        """
        从 Archive 页面解析文章链接，匹配当日日期。
        
        Args:
            html: Archive 页面 HTML
            target_date: 目标日期字符串，如 "Mar 30, 2026"，None 则使用今天
            
        Returns:
            匹配的文章列表 [{title, subtitle, date, url}]
        """
        if target_date is None:
            target_date = self._get_today_str()

        soup = BeautifulSoup(html, "lxml")
        articles = []

        # beehiiv Archive 页面结构：每篇文章是带日期+标题的链接
        # 查找所有文章条目 - 通常在 <article> 或链接列表中
        # 策略 1: 查找包含日期的链接元素
        for link in soup.find_all("a", href=True):
            href = link["href"]
            # 文章链接格式: /p/article-slug
            if "/p/" not in href:
                continue

            text = link.get_text(strip=True)
            if not text:
                continue

            # 尝试从文本中提取日期
            # 格式: "Mar 26, 2026Google's Pied Piper momentPLUS: ..."
            date_match = re.match(
                r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},\s+\d{4})",
                text
            )
            if not date_match:
                continue

            article_date = date_match.group(1)
            # 规范化日期（去除前导零的差异）
            parsed_target = self._parse_date(target_date)
            parsed_article = self._parse_date(article_date)

            if parsed_target and parsed_article and parsed_target.date() == parsed_article.date():
                remaining = text[len(article_date):]

                # 尝试分离标题和副标题
                # 通常格式: "TitlePLUS: Subtitle"
                plus_match = re.split(r"PLUS:\s*", remaining, maxsplit=1)
                title = plus_match[0].strip()
                subtitle = f"PLUS: {plus_match[1].strip()}" if len(plus_match) > 1 else ""

                full_url = href if href.startswith("http") else f"{self.base_url}{href}"

                articles.append({
                    "title": title,
                    "subtitle": subtitle,
                    "date": article_date,
                    "url": full_url,
                })

        # 去重（同一链接可能出现多次）
        seen_urls = set()
        unique = []
        for a in articles:
            if a["url"] not in seen_urls:
                seen_urls.add(a["url"])
                unique.append(a)

        return unique

    def _extract_article_content(self, html: str) -> str:
        """
        从文章详情页提取正文内容。
        过滤掉导航、广告、赞助内容等。
        """
        soup = BeautifulSoup(html, "lxml")

        # 移除不需要的元素
        for tag in soup.find_all(["nav", "header", "footer", "script", "style"]):
            tag.decompose()

        # 查找文章主体内容
        # beehiiv 文章通常在特定的 div 中
        content_area = None

        # 策略 1: 查找 post body 区域
        for selector in [
            "div.post-body",
            "div[class*='post-content']",
            "div[class*='body']",
            "article",
            "div.entry-content",
        ]:
            content_area = soup.select_one(selector)
            if content_area:
                break

        # 策略 2: 如果没找到特定区域，用主内容
        if not content_area:
            content_area = soup.find("main") or soup.body

        if not content_area:
            return ""

        # 提取文本，保留段落结构
        paragraphs = []
        for elem in content_area.find_all(
            ["p", "h1", "h2", "h3", "h4", "h5", "li"]
        ):
            text = elem.get_text(strip=True)
            if not text:
                continue

            # 过滤广告/赞助/导航内容
            skip_patterns = [
                r"This is sponsored",
                r"Subscribe",
                r"Sign up",
                r"Join Free",
                r"Powered by beehiiv",
                r"Privacy policy",
                r"Terms of use",
                r"absolute fire",
                r"do better",
                r"took the L",
                r"participate in polls",
                r"Sponsor AI Valley",
                r"THAT\'?S ALL FOR TODAY",
            ]
            if any(re.search(p, text, re.IGNORECASE) for p in skip_patterns):
                continue

            # 标记标题
            tag_name = elem.name
            if tag_name in ["h1", "h2", "h3", "h4", "h5"]:
                paragraphs.append(f"\n## {text}\n")
            elif tag_name == "li":
                paragraphs.append(f"- {text}")
            else:
                paragraphs.append(text)

        return "\n\n".join(paragraphs)

    async def scrape_today(self, target_date: str | None = None) -> list[Article]:
        """
        抓取当日文章的完整流程。
        
        Args:
            target_date: 可选，指定目标日期，格式 "Mar 30, 2026"
            
        Returns:
            Article 列表
        """
        date_display = target_date or self._get_today_str()
        logger.info(f"🔍 开始抓取 {date_display} 的文章...")

        # 1. 获取 Archive 页面
        try:
            archive_html = await self.fetch_page(self.archive_url)
        except httpx.HTTPError as e:
            logger.error(f"❌ 获取 Archive 页面失败: {e}")
            return []

        # 2. 解析文章链接
        article_links = self._extract_article_links(archive_html, target_date)
        if not article_links:
            logger.warning(f"⚠️ {date_display} 没有找到新文章（可能是周末或假期）")
            return []

        logger.info(f"📰 找到 {len(article_links)} 篇文章")

        # 3. 逐篇抓取正文
        articles = []
        for link_info in article_links:
            logger.info(f"  📄 正在抓取: {link_info['title']}")
            try:
                article_html = await self.fetch_page(link_info["url"])
                content = self._extract_article_content(article_html)

                if content:
                    articles.append(Article(
                        title=link_info["title"],
                        subtitle=link_info["subtitle"],
                        date=link_info["date"],
                        url=link_info["url"],
                        raw_content=content,
                    ))
                    logger.info(f"  ✅ 成功提取 {len(content)} 字符")
                else:
                    logger.warning(f"  ⚠️ 未能提取到有效内容: {link_info['url']}")

            except httpx.HTTPError as e:
                logger.error(f"  ❌ 抓取失败: {link_info['url']} - {e}")
                continue

        logger.info(f"✅ 共成功抓取 {len(articles)} 篇文章")
        return articles
