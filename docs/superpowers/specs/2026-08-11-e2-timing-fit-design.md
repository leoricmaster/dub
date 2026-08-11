# E2 — Timing-Fit（调速对齐）Design

- **Date:** 2026-08-11
- **Status:** Approved (pending implementation)
- **Related:** `BACKLOG.md` E2 · `ARCHITECTURE.md` "时长对齐"

## 问题

中文 TTS clip 必须落在段的 `[start_ms, end_ms]` 窗口内（窗口来自英文 ASR 时间戳）。
但译文长度与 TTS 时长都**与原片窗口无关**，所以 clip 会溢出 → mix 按 `start_ms` 贴 clip 时
撞进下一段 → 叠音、听不清。`dub.timing` 目前只能**检测**溢出（告警）；本设计**修复**它。

业界框架：配音的 isochrony / time-fitting 约束。真人配音在**文本层**解决（改编师重写至合身）；
AI 配音用分层阶梯——时长感知翻译 → TTS 语速 → 保音高时间拉伸（ffmpeg `atempo`）→ 严重时重译。

## 目标

**保证不变量：每条中文 clip 时长 ≤ 段窗口（+容差）。** 消除叠音；最小化 API 成本与音质损失。

**非目标：** 唇形同步；批量/并行调用。

## 设计：三级升级阶梯

### Rung ① — 字数预算重译（翻译期，最省钱，主防线）
- 翻译后逐段：`budget = ⌈max_chars_per_second × duration_sec⌉`；`len(text_zh) > budget` 则用**硬字数预算**重译该段。
- 位置：`stages/translate.py`（编排）+ `providers/deepseek_translate.py`（hard-budget 调用）。
- **只在翻译实际执行（新鲜）时跑** → text_zh 先落盘再生成 clip，杜绝 clip 与文本错配。
- 限一次重试；残留交给 ②③。

### Rung ② — TTS 调速重合成（小幅残差，干净）
- TTS 后实测 clip vs 窗口。`required_speed = voice.speed × clip_ms / window_ms`。
- `required_speed ≤ max_speed(1.2)` → 调 MiniMax 用 `voice.model_copy(speed=required)` 重合成。
- `required_speed > max_speed`（触顶）→ 仍在 `max_speed` 合成一次（最干净地把残差压到最小），再把剩余交给 ③。
- 即：每条溢出 clip 恰好多花**一次** MiniMax 调用，随后重测。**provider 无需重构。**
- 质量优先：保留此级（原生快速语流最自然），让 ③ 的 atempo factor 尽量小。

### Rung ③ — ffmpeg `atempo` 精确对齐（保音高、不丢字、保证不变量）
- ② 之后任何残差溢出（或 ② 触顶）：`atempo` factor = `clip_ms / window_ms`，精确压进窗口。
- 保音高（非 pydub `speedup` 变调）；项目本就依赖 ffmpeg。② 已吸收大头 → factor 小、听感干净。

### 截断 — 仅退化段
- 窗口 `< min_window_ms(200)` 或所需 atempo `> max_atempo(1.5)`：截断到窗口 + 告警。
- 正文段几乎不触发（① 已挡住严重超长）。

## 模块边界（为可测性而切）

- **`dub/timing.py`**（纯函数，扩展现有，零外部依赖）
  新增：`char_budget`、`fits_char_budget`、`over_budget_segments`、`required_speed`、`atempo_factor`。
- **`dub/remediate.py`**（新；编排 + wav 操作，注入 provider 函数）
  `truncate_wav`（stdlib wave+array，淡出）、`atempo_fit`（ffmpeg）、
  `remediate_translation`、`remediate_clips`、`Report`。
- `stages/translate.py`：接入 ①。
- `pipeline.py`：TTS 后接入 ②③（替换当前"仅告警"）。

## 配置（全部进入 `config_signature` → 改即失效缓存）

- `TranslateConfig`：复用 `max_chars_per_second`，加 `refit: bool = True`。
- `TTSConfig`：加 `max_speed: float = 1.2`。
- `RemediateConfig`（新）：`tolerance_ms=50`、`min_window_ms=200`、`max_atempo=1.5`。

## 数据流 / 缓存

- ① 把修后 text_zh 写回 `segments_zh.json` → resume 跳过翻译，TTS 用最终文本生成 clip。
- ②③ 覆盖写回 `tts_clips/*.wav` → resume 跳过 TTS。
- 幂等；中断后续跑安全。

## 测试（TDD；快车道注入假函数，不碰真实 API）

- **纯函数（timing）**：`char_budget`/`fits_char_budget`/`required_speed`/`atempo_factor`，含 0 窗口与边界。
- **`truncate_wav`**：`make_wav(3s)→1s` 实测 1000ms。
- **`atempo_fit`**：`make_wav(2s)→1000ms`（真实 ffmpeg，项目已依赖）。
- **`remediate_translation`**：注入假 `retranslate_fn`（返回更短文本）→ 超预算段被改、报表正确。
- **`remediate_clips`**：注入假 `resynth_fn`（可控时长 wav）+ fit_fn → 覆盖 ②命中、②触顶后③、退化截断、无溢出 no-op、报表字段。
- **`@pytest.mark.live`（默认跳过）**：MiniMax speed 1.0 vs 1.2（时长反比）；DeepSeek hard-budget（输出变短）。

## 不做（YAGNI）

超过 1 次的 re-prompt；atempo 之外的本地拉伸；并行调用；mix 后检测；唇形同步。
