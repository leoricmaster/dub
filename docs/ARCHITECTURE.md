# Architecture — dub

> 六阶段串接，配置驱动，hash 缓存，断点续跑。对应 v0.1。

## 总览

```mermaid
flowchart LR
  MKV[input.mkv] --> EX[extract] --> TR[transcribe] --> TL[translate] --> TTS[tts] --> MX[mix] --> MUX[mux] --> OUT[output/*.zh.mkv]
  C[(.dub-cache 每阶段产物)] -.命中即跳过.-> EX & TR & TL & TTS & MX & MUX
```

`dub zh` 跑完整链路；各阶段产物落盘到 per-input 工作目录，命中即跳过。分层：`pipeline.py` 编排 → `stages/` 阶段逻辑 → `providers/` 厂商调用。

## 阶段

| # | 阶段 | 输入 | 输出 | 实现 |
|---|---|---|---|---|
| 1 | extract | 容器 | `audio.wav` 16k mono | ffmpeg |
| 2 | transcribe | audio | `Segment[]` 带时间戳 | DashScope Paraformer-v2（音频传 OSS） |
| 3 | translate | `Segment[]` | 填 `text_zh` | DeepSeek（OpenAI 兼容） |
| 4 | tts | `Segment[]`+音色 | `tts_clips/*.wav` | MiniMax T2A |
| 5 | mix | audio+clips | `zh_audio.wav` | pydub overlay |
| 6 | mux | 原片+zh_audio | `*.zh.mkv` | ffmpeg 加轨 |

## 关键抽象

- **`Segment`**（`id, text_src, text_zh, start_ms, end_ms`）：贯穿全链路的最小单元，时间戳是唯一锚点。
- **`JobContext`**：单输入的可变状态。
- **`AppConfig`**：`default.yaml`（阶段参数）+ `voices.yaml`（音色）+ `.env`（密钥）。

## 缓存与续跑

目录键 = `input_hash(文件+voice) + sha1(全阶段配置)[:12]`。配置变 → 新目录，安全重跑。每阶段查产物存在 + `resume` 即跳过；`--no-resume` 强制全跑。

## provider 解耦

`stages/` 按 `cfg.provider` 派发到 `providers/`。换厂商 = 加一个 provider 文件 + 改配置。

## 关键决策

| 决策 | 选择 | 理由 |
|---|---|---|
| 全云 vs 本地模型 | 全云 | 国内可达、无 GPU 门槛 |
| 缓存粒度 | 阶段级文件 | 简单；改配置自动失效 |
| 输出 | 附加 mkv 轨 | 不动原片，可回退可对比 |

## 已知风险

- **时长对齐：已检测、未自动修复（头号）**：`dub.timing` 在 TTS 后量测 clip 并对溢出告警；但 mix 仍在 `start_ms` 直接贴 clip，溢出仍会灌进下一段，自动修复（调速/精简/拉伸）待 BACKLOG E2。
- **翻译地道度未验证**：当前 deepseek-chat + 基础 prompt。→ E1
- **音色是占位值**：`voices.yaml` 的 voice_id 未校验。→ E3
- **核心已测、provider 未测**：cache/models/timing 等纯函数已有单测（快车道 33 绿）；provider 改字段仍会静默坏掉，契约测试待 E4。
- **混音无分离**：整体 -12dB，中文段英文旁白仍漏出。→ P2
- **OSS 临时对象**：失败路径下是否回收未验证。

## 运行环境

Python ≥ 3.10；ffmpeg 在 PATH；国内网络。P2 起可选 AutoDL 跑 Demucs。
