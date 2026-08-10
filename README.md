# dub

给没有中文配音的优秀纪录片加 AI 中文配音，让孩子能看。原视频不动，中文作为附加音轨写入 mkv。个人 CLI，全国内云 API。

## 工作流

```
input.mkv
  → extract     (ffmpeg 抽轨)
  → transcribe  (阿里云 Paraformer-v2，英文转写带时间戳)
  → translate   (DeepSeek，时长感知断句)
  → tts         (MiniMax，中文纪录片音色)
  → mix         (中文配音叠加原音轨，原音衰减 -12dB)
  → mux         (写入 mkv 作为新音轨)
```

每阶段产物按输入文件 hash + 配置 hash 缓存到 `.dub-cache/`，断点续跑、改配置只重跑受影响阶段。

## 快速开始

**前置**：Python ≥ 3.10 · ffmpeg / ffprobe 在 PATH · 国内网络

```bash
cd dub
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
```

申请四组 key（都有免费额度或新用户优惠）：

| 服务 | 申请地址 | 用途 |
|---|---|---|
| **DeepSeek** | https://platform.deepseek.com/ | 翻译（OpenAI 兼容） |
| **MiniMax** | https://platform.minimaxi.com/ | 中文 TTS（同时拿 Group ID） |
| **阿里云 DashScope** | https://bailian.console.aliyuncs.com/ | 英文 ASR |
| **阿里云 OSS** | https://oss.console.aliyuncs.com/ | 上传音频给 ASR 读 |

阿里云 OSS：建私有 Bucket → RAM 建 AccessKey（勿用主账号）→ 记下 ID / Secret / Bucket / Endpoint。

```bash
cp .env.example .env   # 填入四组 key
dub voices             # 验证：列出 nature/food/science/history 预设
```

## 使用

```bash
dub zh ~/The.Blue.Planet.E01.mkv --voice nature        # 完整流程
dub translate ~/The.Blue.Planet.E01.mkv --voice nature  # 只翻译预览，不花 TTS 钱
dub voices                                              # 列出音色预设
dub zh input.mkv --voice nature --no-resume             # 改配置后强制重跑
```

输出 `output/<input-stem>.zh.mkv`：原片 + 一条默认不抢占的中文音轨。

## 成本

~¥10/集（50 分钟：ASR ¥4 / 翻译 ¥0.3 / TTS ¥5）。翻译便宜且可缓存，反复调译文几乎不花钱。

## 音色

`config/voices.yaml` 里的 voice_id 当前是占位值，跑通后到 MiniMax 控制台试听候选并更新映射。

## 文档

- [PRD](docs/PRD.md) — 定位、目标、需求
- [架构](docs/ARCHITECTURE.md) — 阶段、缓存机制、已知风险
- [Backlog](docs/BACKLOG.md) — 路线图与任务

## 故障排查

**ASR 报「OSS object not accessible」** — Bucket 可私有，但签名 URL 必须由你的 AccessKey 生成；确认 `.env` 中 `OSS_ENDPOINT` 与 `OSS_REGION` 一致。

**MiniMax 报「unauthorized」** — 同时需要 API Key（Bearer）和 Group ID（URL 参数），都在 `.env`。

**ffmpeg 找不到** — `brew install ffmpeg`（macOS）或对应包管理器。
