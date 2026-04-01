# 🎙️ AI 日报 - 每日 AI 前沿速递

自动抓取 [The AI Valley](https://www.theaivalley.com/) 每日 AI 新闻 → DeepSeek 翻译整理为中文新闻简报 → edge-tts 语音合成 → 发布到 Apple Podcasts。

## ✨ 特性

- 🔍 **自动抓取**：每日从 AI Valley Archive 抓取最新 AI 新闻
- 🤖 **智能翻译**：DeepSeek API 翻译并整理为中文新闻简报风格
- 🎙️ **语音合成**：edge-tts 生成自然流畅的中文播报音频
- 📡 **自动发布**：生成 Apple Podcasts 兼容 RSS Feed
- ⏰ **全自动化**：GitHub Actions 每日 7:00 AM (CST) 自动运行

## 🏗️ 架构

```
Cron 7:00AM → Scraper → DeepSeek 翻译 → edge-tts 语音 → RSS Feed → GitHub Pages → Apple Podcasts
```

## 📁 项目结构

```
ai-daily-podcast/
├── .github/workflows/
│   └── daily_podcast.yml    # GitHub Actions 工作流
├── config/
│   └── settings.yaml        # 配置文件
├── src/
│   ├── scraper.py           # 网页抓取
│   ├── translator.py        # DeepSeek 翻译
│   ├── tts.py               # 语音合成
│   ├── rss_generator.py     # RSS Feed 生成
│   └── pipeline.py          # 流程编排
├── assets/
│   └── cover.jpg            # 播客封面
├── main.py                  # 入口
└── requirements.txt         # 依赖
```

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 设置环境变量

```bash
# DeepSeek API Key
export DEEPSEEK_API_KEY="your-api-key"

# GitHub Pages 基础 URL（可选，GitHub Actions 自动设置）
export PODCAST_BASE_URL="https://your-username.github.io/ai-daily-podcast"
```

### 3. 本地运行

```bash
# 抓取当天文章
python main.py

# 抓取指定日期
python main.py --date "Mar 26, 2026"

# 列出可用的中文语音
python main.py --list-voices
```

### 4. 部署到 GitHub

1. 仓库已创建: `https://github.com/superheroyly/AI-DAILY`
2. Secret 已配置: `DEEPSEEK_API_KEY`
3. 推送代码:
   ```bash
   git push -u origin main
   ```
4. 推送后，在 GitHub 仓库 Settings → Pages 中启用 GitHub Pages（源选 `gh-pages` 分支）
5. 手动触发一次 Actions workflow，等待完成
6. 访问 `https://superheroyly.github.io/AI-DAILY/feed/podcast.xml` 确认 RSS 正常

### 5. 提交到 Apple Podcasts

1. 登录 [Apple Podcasts Connect](https://podcastsconnect.apple.com/)
2. 添加新节目 → 选择 RSS Feed
3. 输入 RSS Feed URL：`https://superheroyly.github.io/AI-DAILY/feed/podcast.xml`
4. 等待 Apple 审核（通常 1-10 个工作日）
5. 审核通过后，每日新 episode 会自动被 Apple 拉取

## ⚙️ 配置说明

编辑 `config/settings.yaml` 可自定义：

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `tts.voice` | TTS 语音 | `zh-CN-XiaoxiaoNeural` (女声) |
| `tts.rate` | 语速 | `+0%` |
| `deepseek.model` | LLM 模型 | `deepseek-chat` |
| `deepseek.temperature` | 创造性 | `0.7` |
| `podcast.title` | 播客标题 | `AI 日报` |

## 📝 License

MIT
