"""
tts.py - 语音合成模块
使用 edge-tts 将中文新闻简报脚本转换为 MP3 音频
"""

import re
import asyncio
import logging
from pathlib import Path

import edge_tts

logger = logging.getLogger(__name__)


class TTSEngine:
    """基于 edge-tts 的语音合成引擎"""

    def __init__(self, config: dict):
        tts_cfg = config["tts"]
        self.voice = tts_cfg["voice"]
        self.rate = tts_cfg["rate"]
        self.volume = tts_cfg["volume"]
        self.pause_ms = tts_cfg["paragraph_pause_ms"]

    def _prepare_ssml(self, text: str) -> str:
        """
        将纯文本脚本转换为 SSML 格式，添加停顿控制。
        
        处理逻辑：
        1. [pause] 标记 → SSML <break> 停顿
        2. 段落间 → 添加适当停顿
        3. 清理不适合朗读的内容
        """
        # 清理文本
        text = text.strip()

        # 移除 markdown 格式（以防 LLM 仍然生成）
        text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)  # **bold**
        text = re.sub(r"\*(.+?)\*", r"\1", text)      # *italic*
        text = re.sub(r"#{1,6}\s*", "", text)          # ## headings
        text = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", text)  # [link](url)

        # 替换 [pause] 标记为 SSML break
        text = re.sub(
            r"\[pause\]",
            f'<break time="{self.pause_ms}ms"/>',
            text,
            flags=re.IGNORECASE,
        )

        # 在双换行（段落分隔）处插入停顿
        text = re.sub(
            r"\n\s*\n",
            f'\n<break time="{self.pause_ms}ms"/>\n',
            text,
        )

        # 构建 SSML
        ssml = f"""<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis"
       xmlns:mstts="https://www.w3.org/2001/mstts"
       xml:lang="zh-CN">
    <voice name="{self.voice}">
        <prosody rate="{self.rate}" volume="{self.volume}">
            {text}
        </prosody>
    </voice>
</speak>"""

        return ssml

    async def synthesize(self, text: str, output_path: str) -> str:
        """
        将文本合成为 MP3 音频文件。
        
        Args:
            text: 要合成的中文文本
            output_path: 输出 MP3 文件路径
            
        Returns:
            生成的 MP3 文件路径
        """
        if not text:
            raise ValueError("合成文本不能为空")

        # 确保输出目录存在
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        logger.info(f"🎙️ 开始语音合成...")
        logger.info(f"   声音: {self.voice}")
        logger.info(f"   文本长度: {len(text)} 字符")

        # 尝试使用 SSML（更好的停顿控制）
        # 如果 SSML 失败则回退到纯文本
        try:
            # 先清理文本中的 [pause] 标记为实际停顿文本
            clean_text = re.sub(r"\[pause\]", "。", text, flags=re.IGNORECASE)
            # 移除 markdown 格式
            clean_text = re.sub(r"\*\*(.+?)\*\*", r"\1", clean_text)
            clean_text = re.sub(r"\*(.+?)\*", r"\1", clean_text)
            clean_text = re.sub(r"#{1,6}\s*", "", clean_text)
            clean_text = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", clean_text)

            communicate = edge_tts.Communicate(
                text=clean_text,
                voice=self.voice,
                rate=self.rate,
                volume=self.volume,
            )
            await communicate.save(output_path)

            # 验证文件生成
            file_size = Path(output_path).stat().st_size
            logger.info(f"✅ 语音合成完成")
            logger.info(f"   输出文件: {output_path}")
            logger.info(f"   文件大小: {file_size / 1024 / 1024:.2f} MB")

            return output_path

        except Exception as e:
            logger.error(f"❌ 语音合成失败: {e}")
            raise

    async def list_voices(self, language: str = "zh") -> list[dict]:
        """列出可用的中文语音"""
        voices = await edge_tts.list_voices()
        return [v for v in voices if v["Locale"].startswith(language)]
