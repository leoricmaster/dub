# dub

为纪录片视频生成中文 AI 配音音轨。原视频不动，中文音轨作为额外轨道写入 mkv。

## 工作流

```
input.mkv
  → extract     (ffmpeg 抽轨)
  → transcribe  (阿里云通义听悟 Paraformer-v2，英文转写带时间戳)
  → translate   (DeepSeek-V3，时长感知断句)
  → tts         (MiniMax T2A-01，中文纪录片音色)
  → mix         (中文配音叠加原音轨，原音衰减 -12dB)
  → mux         (写入 mkv 作为新音轨)
```

每阶段产物按输入文件 hash + 配置 hash 缓存到 `.dub-cache/`，断点续跑、改配置只重跑受影响阶段。

## 前置条件

- Python ≥ 3.10
- ffmpeg / ffprobe（在 PATH 中）
- 国内网络（直连阿里云 / DeepSeek / MiniMax）

## 一次性配置

### 1. 安装

```bash
cd dub
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 2. 申请 API key

按顺序申请（都有免费额度或新用户优惠）：

| 服务 | 申请地址 | 用途 |
|---|---|---|
| **DeepSeek** | https://platform.deepseek.com/ | 翻译（OpenAI 兼容协议） |
| **MiniMax** | https://platform.minimaxi.com/ | 中文 TTS（注意同时拿到 Group ID） |
| **阿里云 DashScope** | https://dashscope.console.aliyun.com/ | 英文 ASR（Paraformer-v2） |
| **阿里云 OSS** | https://oss.console.aliyun.com/ | 上传音频给 ASR 读取 |

阿里云 OSS 配置步骤：

1. 创建 Bucket（区域选离你近的，权限选 **私有**）
2. 通过 RAM 创建 AccessKey（不要用主账号 key）
3. 记下 `AccessKey ID` / `AccessKey Secret` / `Bucket 名` / `Endpoint`

### 3. 写 `.env`

```bash
cp .env.example .env
# 编辑 .env 填入四组 key
```

### 4. 验证

```bash
dub voices
# 应列出 nature / food / science / history 四个预设
```

## 使用

```bash
# 完整流程
dub zh ~/Downloads/The.Blue.Planet.E01.mkv --voice nature

# 只翻译预览（不调 TTS，不花 TTS 钱）
dub translate ~/Downloads/The.Blue.Planet.E01.mkv --voice nature

# 列出音色预设
dub voices

# 改了配置后强制重跑
dub zh input.mkv --voice nature --no-resume
```

输出文件：`output/<input-stem>.zh.mkv`，原视频基础上多了一条中文音轨 + 默认不抢占默认轨。

## 音色预设

定义在 `config/voices.yaml`。当前 4 个预设的 voice_id 是占位值——首次跑通后建议到 https://platform.minimaxi.com/document/T2A%20V2 听一遍候选音色，再回头更新映射。

新增纪录片类型 = 在 yaml 里加一段：

```yaml
my_new_style:
  provider: minimax
  voice_id: <voice-id-from-minimax>
  speed: 0.95
  vol: 1.0
  pitch: 0
```

## 单集成本估算

50 分钟纪录片（参考值）：

| 阶段 | 成本 |
|---|---|
| 通义听悟 ASR | ~¥4 |
| DeepSeek 翻译 | ~¥0.3 |
| MiniMax TTS（~15k 字符） | ~¥5 |
| **合计** | **~¥10/集** |

## 路线图

**P1（当前，MVP）**
- 全云方案，无本地计算压力
- 七阶段串接，配置驱动，断点续跑
- 简单混音（原音整体衰减，不做精确 BGM 分离）

**P2（生产化）**
- AutoDL SSH + Demucs v4 远程分离人声/BGM
- BGM ducking（中文段期间 BGM 自动降低，间隙恢复）
- 术语表支持（物种名/人名/地名翻译一致性）
- MiniMax 音色试听与映射固化
- 错误恢复 + 重试优化

**P3（增强）**
- 批量处理（整个目录）
- 中文字幕导出（SRT）
- 多 provider 切换（阿里云 CosyVoice / 火山引擎 TTS 备选）
- Web UI（可选）

## 故障排查

**ASR 报错「OSS object not accessible」**
检查 OSS Bucket 权限。Bucket 本身可以是私有，但签名 URL 必须由你的 AccessKey 生成。确认 `.env` 中 OSS_ENDPOINT 和 OSS_REGION 一致。

**MiniMax 报错「unauthorized」**
MiniMax 同时需要 API Key（Bearer）和 Group ID（URL 参数），两者都在 `.env` 中配置。

**ffmpeg 找不到**
`brew install ffmpeg`（macOS）或对应平台的包管理器。

**字幕长度超过原时长**
调小 `config/default.yaml` 中 `translate.max_chars_per_second`（默认 3.5），或换 `deepseek-reasoner` 模型提升翻译精炼度。

**音质/翻译质量不满意**
- 翻译问题：先 `dub translate` 预览，确认是 ASR 还是翻译问题
- 音色问题：更新 `voices.yaml` 的 voice_id
- 术语问题：P2 会加术语表，目前可在 LLM prompt 里直接补充

## 项目结构

```
dub/
├── config/
│   ├── default.yaml         # 各阶段参数
│   └── voices.yaml          # 音色预设
├── src/dub/
│   ├── cli.py               # typer CLI 入口
│   ├── pipeline.py          # 六阶段编排
│   ├── config.py            # pydantic 配置加载
│   ├── cache.py             # hash-based 缓存
│   ├── models.py            # Segment / AudioTrack / JobContext
│   ├── stages/              # 每阶段一个文件
│   └── providers/           # 每厂商一个文件
└── tests/
```
