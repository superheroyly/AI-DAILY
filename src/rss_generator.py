"""
rss_generator.py - RSS Feed 生成器
生成符合 Apple Podcasts 要求的 RSS 2.0 XML Feed

使用 lxml 替代 stdlib xml.etree 以正确处理命名空间，
避免重复 xmlns 属性导致解析失败。
"""

import os
import logging
from pathlib import Path
from datetime import datetime, timezone, timedelta

from lxml import etree
from mutagen.mp3 import MP3

logger = logging.getLogger(__name__)

CST = timezone(timedelta(hours=8))

# 命名空间
ITUNES_NS = "http://www.itunes.apple.com/dtds/podcast-1.0.dtd"
CONTENT_NS = "http://purl.org/rss/1.0/modules/content/"

NSMAP = {
    "itunes": ITUNES_NS,
    "content": CONTENT_NS,
}


def _itunes(tag: str) -> str:
    """生成 iTunes 命名空间标签"""
    return f"{{{ITUNES_NS}}}{tag}"


def _content(tag: str) -> str:
    """生成 Content 命名空间标签"""
    return f"{{{CONTENT_NS}}}{tag}"


def _format_rfc2822(dt: datetime) -> str:
    """格式化日期为 RFC 2822（RSS 标准格式）"""
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    day_name = days[dt.weekday()]
    month_name = months[dt.month - 1]
    tz_offset = dt.strftime("%z")
    return f"{day_name}, {dt.day:02d} {month_name} {dt.year} {dt.hour:02d}:{dt.minute:02d}:{dt.second:02d} {tz_offset}"


def _format_duration(seconds: float) -> str:
    """格式化音频时长为 HH:MM:SS 或 MM:SS"""
    total = int(seconds)
    hours = total // 3600
    minutes = (total % 3600) // 60
    secs = total % 60
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


class RSSGenerator:
    """Apple Podcasts 兼容 RSS Feed 生成器"""

    def __init__(self, config: dict):
        self.config = config
        self.podcast = config["podcast"]
        self.output_cfg = config["output"]

        # 优先级: 环境变量 > config 文件 > 硬编码默认值
        self.base_url = os.environ.get(
            "PODCAST_BASE_URL",
            config.get("github_pages", {}).get(
                "base_url",
                "https://superheroyly.github.io/AI-DAILY"
            ),
        )

        self.feed_path = os.path.join(
            self.output_cfg["feed_dir"],
            self.output_cfg["feed_filename"],
        )

    def _get_audio_info(self, audio_path: str) -> dict:
        """获取 MP3 文件信息（大小、时长）"""
        p = Path(audio_path)
        file_size = p.stat().st_size

        try:
            audio = MP3(audio_path)
            duration = audio.info.length
        except Exception:
            duration = 0

        return {
            "size": file_size,
            "duration": duration,
            "duration_str": _format_duration(duration),
        }

    def _create_channel(self) -> etree._Element:
        """创建 RSS channel 根元素（使用 lxml）"""
        rss = etree.Element("rss", version="2.0", nsmap=NSMAP)
        channel = etree.SubElement(rss, "channel")

        # 必要 channel 标签
        etree.SubElement(channel, "title").text = self.podcast["title"]
        etree.SubElement(channel, "description").text = self.podcast["description"]
        etree.SubElement(channel, "link").text = self.base_url
        etree.SubElement(channel, "language").text = self.podcast["language"]
        etree.SubElement(channel, "generator").text = "AI Daily Podcast Generator"

        # 最后构建时间
        now = datetime.now(CST)
        etree.SubElement(channel, "lastBuildDate").text = _format_rfc2822(now)

        # iTunes 标签
        etree.SubElement(channel, _itunes("author")).text = self.podcast["author"]
        etree.SubElement(channel, _itunes("subtitle")).text = self.podcast.get("subtitle", "")
        etree.SubElement(channel, _itunes("summary")).text = self.podcast["description"]
        etree.SubElement(channel, _itunes("explicit")).text = str(self.podcast["explicit"]).lower()

        # 封面图片
        cover_url = f"{self.base_url}/{self.podcast['cover_filename']}"
        etree.SubElement(channel, _itunes("image"), href=cover_url)

        # 分类
        etree.SubElement(channel, _itunes("category"), text=self.podcast["category"])

        # Owner
        owner = etree.SubElement(channel, _itunes("owner"))
        etree.SubElement(owner, _itunes("name")).text = self.podcast["author"]
        etree.SubElement(owner, _itunes("email")).text = self.podcast["email"]

        etree.SubElement(channel, _itunes("type")).text = "episodic"

        return rss

    def _load_existing_feed(self) -> tuple[etree._Element | None, list[etree._Element]]:
        """
        加载已有的 RSS Feed，提取现有 episodes。

        Returns:
            (rss_root, existing_items)
        """
        if not Path(self.feed_path).exists():
            return None, []

        try:
            tree = etree.parse(self.feed_path)
            root = tree.getroot()
            channel = root.find("channel")
            if channel is None:
                return None, []

            items = channel.findall("item")
            return root, items

        except Exception as e:
            logger.warning(f"⚠️ 加载现有 Feed 失败，将创建新 Feed: {e}")
            return None, []

    @staticmethod
    def _clean_description(text: str) -> str:
        """清理描述文本中的 [pause] 标记等"""
        import re
        text = re.sub(r'\s*\[pause\]\s*', ' ', text, flags=re.IGNORECASE)
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    def _create_episode_item(
        self,
        date: str,
        title: str,
        description: str,
        audio_filename: str,
        audio_info: dict,
    ) -> etree._Element:
        """创建单个 episode <item> 元素"""
        item = etree.Element("item")

        clean_desc = self._clean_description(description)
        episode_title = f"{self.podcast['title']} {date}"
        etree.SubElement(item, "title").text = episode_title
        etree.SubElement(item, "description").text = clean_desc

        # 音频文件 enclosure
        audio_url = f"{self.base_url}/audio/{audio_filename}"
        etree.SubElement(item, "enclosure", url=audio_url, length=str(audio_info["size"]), type="audio/mpeg")

        # GUID - 唯一标识
        guid = etree.SubElement(item, "guid", isPermaLink="false")
        guid.text = f"ai-daily-{date}"

        # 发布时间
        pub_date = datetime.strptime(date, "%Y-%m-%d").replace(
            hour=7, minute=0, second=0, tzinfo=CST
        )
        etree.SubElement(item, "pubDate").text = _format_rfc2822(pub_date)

        # iTunes 标签
        etree.SubElement(item, _itunes("title")).text = episode_title
        etree.SubElement(item, _itunes("summary")).text = clean_desc[:300]
        etree.SubElement(item, _itunes("duration")).text = audio_info["duration_str"]
        etree.SubElement(item, _itunes("explicit")).text = "false"
        etree.SubElement(item, _itunes("episodeType")).text = "full"

        return item

    def generate_feed(
        self,
        date: str,
        description: str,
        audio_path: str,
    ) -> str:
        """
        生成或更新 RSS Feed。

        Args:
            date: 日期字符串 "YYYY-MM-DD"
            description: episode 描述（简报前200字摘要）
            audio_path: MP3 文件路径

        Returns:
            生成的 Feed 文件路径
        """
        logger.info(f"📡 正在生成 RSS Feed...")

        # 确保输出目录存在
        Path(self.feed_path).parent.mkdir(parents=True, exist_ok=True)

        # 获取音频信息
        audio_info = self._get_audio_info(audio_path)
        audio_filename = Path(audio_path).name

        logger.info(f"   音频时长: {audio_info['duration_str']}")
        logger.info(f"   音频大小: {audio_info['size'] / 1024 / 1024:.2f} MB")

        # 加载或创建 Feed
        existing_root, existing_items = self._load_existing_feed()

        # 检查是否已有同日 episode（避免重复）
        for item in existing_items:
            guid = item.find("guid")
            if guid is not None and guid.text == f"ai-daily-{date}":
                logger.info(f"   ⚠️ {date} 的 episode 已存在，将更新")
                existing_items.remove(item)
                break

        # 创建新的 Feed 结构
        rss = self._create_channel()
        channel = rss.find("channel")

        # 创建新 episode
        new_item = self._create_episode_item(
            date=date,
            title=f"AI 日报 {date}",
            description=description,
            audio_filename=audio_filename,
            audio_info=audio_info,
        )

        # 将新 episode 插入最前面，再追加旧 episodes
        channel.append(new_item)
        for item in existing_items:
            channel.append(item)

        # 写入文件（lxml 自动处理命名空间，不会产生 duplicate attribute）
        tree = etree.ElementTree(rss)
        with open(self.feed_path, "wb") as f:
            tree.write(
                f,
                xml_declaration=True,
                encoding="UTF-8",
                pretty_print=True,
            )

        logger.info(f"✅ RSS Feed 已生成: {self.feed_path}")
        logger.info(f"   Feed URL: {self.base_url}/feed/{self.output_cfg['feed_filename']}")
        logger.info(f"   Base URL: {self.base_url}")

        return self.feed_path
