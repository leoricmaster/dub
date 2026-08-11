# 设计：让 `nature` 音色更像 BBC 中文纪录片解说

- **日期**：2026-08-11
- **状态**：草案，待评审
- **相关**：[PRD](../../PRD.md) · [BACKLOG E3 音色固化](../../BACKLOG.md) · 提交 `5fc93cc`

## 背景

`dub` 给英文纪录片加中文 AI 配音给孩子看。配音用 MiniMax T2A v2（`speech-2.8-hd`），纪录片预设 `nature`。

上一轮（`5fc93cc`）已为「不像纪录片」改过一次：`nature` 的 `voice_id` 从 `male-qn-yuanbo`（turbo 下实测无效）换成 `presenter_male`（播音男声），模型 `speech-01-turbo → speech-2.8-hd`。**但用户仍不满意。**

校准后的标杆与痛点：

- **标杆**：BBC 中文解说式（中性、沉稳、克制、知识感、不抢戏，类似 *Planet Earth* 中文版旁白）。
- **痛点 1：音质太亮/单薄。** `presenter_male` 是「播音男声」，音色指纹偏亮偏新闻，缺纪录片该有的低沉沉稳。**调参改不了音色本体，只能换 `voice_id`。**
- **痛点 2：情感太干/太平。** 当前 `emotion=neutral` 是 MiniMax 9 种 emotion 里最干的一种。BBC 解说明显更契合 `calm`（平静从容）或 `fluent`（流畅生动）。

MiniMax 官方音色库里**存在现成的纪录片向音色**（「平和旁白：沉稳/大气/磁性，中文普通话」「磁性旁白：低沉浑厚/平稳有力」）。障碍在于：这些 `voice_id` 在 `speech-2.8-hd` 下的确切字符串与有效性**无法在线确认**（官方页被网络策略拦截，且项目现有探针是 turbo 时代结果，hd 支持的音色集可能不同），**只能靠实际合成试听**。

## 目标

- 把 `nature` 预设调到「更像 BBC 中文纪录片解说」，直击音质与情感两个痛点。
- 提供一个**可复用的试听工具**，让「换音色」这件事靠耳朵定，而不是纸上推演。
- 顺带修掉文档滞后（README/BACKLOG 仍写 `male-qn-yuanbo`），并推进 BACKLOG E3。

> **定位：判定实验，而非终局方案。** 本设计的首要目的是用最低成本（几毛钱、半小时）判定 MiniMax 预设里到底有没有能接受的纪录片音色：有 → 固化进 `nature` 收工；没有（作者判断大概率）→ 给出明确依据，转入中长期「本地音色库」路线（见末尾「中长期」）。

## 非目标

- ❌ 声音克隆（PRD 明确排除）。
- ❌ 本轮不动 `food`/`science`/`history` 预设的固化（工具就绪后可后续复用）。
- ❌ 不改主缓存契约：试听产物不进 `.dub-cache`，是临时探索产物。

## 设计

### 新命令 `dub preview-voices`

一句话：**用同一段固定中文旁白，批量合成「候选音色 × 情感」小样到本地，盲听对比。**

```
dub preview-voices [--voices id1,id2,...] [--emotions calm,fluent]
                   [--speed 0.92] [--text "..."]
```

- **复用** `minimax_tts.synthesize_one`；不碰 pipeline 其他阶段，不写主缓存。
- 参数：
  - `--voices`：候选 voice_id 列表，逗号分隔。默认见下。
  - `--emotions`：候选 emotion 列表，逗号分隔。默认 `calm`。
  - `--speed`：试听统一语速，默认 `0.92`（偏从容，便于盲听只聚焦音色+情感）。所有候选共用同一 speed/pitch，保证可比。
  - `--text`：覆盖内置旁白（可选）。
  - `pitch` 固定 `0`，不暴露（YAGNI；选定音色后单独微调）。

### 内置旁白文本

一段原创的 BBC 自然纪录片风中文旁白，有场景、有节奏、能体现沉稳叙事与适度起伏（非纯陈述）：

> 在非洲草原的尽头，雨季的云层正在聚集。一群角马已经在这里等待了数周——它们能嗅到远方的水汽。当第一场雨落下，漫长的迁徙就将开始。这片土地上的每一个生命，都在等待这一刻。

常量定义在 `src/dub/cli.py`（或 `minimax_tts.py`）中，约 80 字、几秒时长。

### 候选矩阵

默认候选（针对「沉稳/旁白/低沉」，基于官方音色库描述 + 项目已有探针）：

| voice_id | 来源/说明 |
|---|---|
| `presenter_male` | 当前基准（播音男声） |
| `male-qn-jingying` | 精英男声，沉稳商务感 |
| `male-qn-yuanbo` | 渊博/纪录片旁白风；turbo 下无效，**hd 待验** |
| `male-qn-badao` | 低沉有力 |

默认矩阵 = 上述 4 个 × `{calm}`，**外加自动追加 `presenter_male×neutral`**（= 用户当前实际听到的效果，作参照锚点）。共 5 个小样。用户可 `--emotions calm,fluent` 扩展。

> 候选清单是探索性的，硬编码在命令里，不开新 config 文件。固化完成后即弃用——YAGNI。

### 输出

- 目录：`output/voice-previews/<YYYYmmdd-HHMMSS>/`（不用 `Date.now()`——用 CLI 进程启动时戳一次，传入）。
- 文件：`<voice_id>__<emotion>.wav`（如 `male-qn-jingying__calm.wav`）。
- 控制台：rich table，列 = `组合 | voice_id | emotion | 状态(ok/skipped) | 文件路径`。

### 错误处理（关键）

- **voice_id 在 hd 下无效**：MiniMax 返回 `base_resp.status_code` 含 `2054`（voice id not exist）。`preview-voices` 必须逐组合 `try/except`，捕获后标记 `skipped` 并记录原因，**继续下一个**，绝不让整命令挂掉。这是上一轮踩过的坑，试听命令的核心价值之一就是把这种不确定性暴露成「跳过」而非「崩溃」。
- emotion 不被接受：同理跳过（实现时若 `calm` 在 hd 下不被接受会在此暴露）。
- API key 缺失：复用现有 `EnvSettings` 检查，友好报错。
- 网络/超时：复用现有 tenacity 6 次重试（已在 `synthesize_one` 上）。

> `synthesize_one` 当前对非音频响应抛 `RuntimeError(f"...{data}")`。preview 需区分「voice_id 无效(2054)」与「真·故障」，实现时在 provider 层加一个明确异常（如 `VoiceIdInvalid`）或让 preview 层解析响应 `base_resp`——详见实现计划。

### 固化流程（人工）

盲听选定后：

1. 用户手动改 `config/voices.yaml` 的 `nature`：`voice_id` + `emotion`（speed/pitch 按需微调）。
2. 命令在末尾打印一份「建议改成」的 yaml 片段，方便复制（不自动覆盖——选哪个是人耳判断，自动写回 config 风险大于收益）。
3. 改完 `dub zh <video> --voice nature --no-resume` 重跑验证（voice 预设变化会令 TTS 阶段缓存失效，只重花 TTS 的钱）。

### 测试

- 单测（不打真实 API）：
  - 候选矩阵展开（含自动追加的 `presenter_male×neutral` 参照）。
  - 输出文件名编码。
  - `2054` 跳过逻辑：mock `synthesize_one` 对某 id 抛 `VoiceIdInvalid`，断言该组合 `skipped`、其余继续。
  - 对照表生成。
- 沿用 `@pytest.mark.live` 门控真实 API 调用。

## 文档同步

固化后一并修订：

- `README.md` §音色：`male-qn-yuanbo` → 实际选定的 voice_id，删掉过时描述。
- `docs/BACKLOG.md` E3：更新 `nature` 固化状态。
- `config/voices.yaml` 顶部注释：补充 hd 模型下实测有效/无效的 voice_id 探针结果。

## 已知不确定性与风险

| 项 | 说明 | 应对 |
|---|---|---|
| 候选 voice_id 在 hd 下的有效性 | 除 `presenter_male` 外均未在 hd 实测 | preview 容错跳过无效 id；以实测结果为准 |
| `emotion` 取值范围 | 第三方文档有出入（`calm/fluent` vs `vivid/whisper`） | 默认 `calm`，不被接受则在 preview 报错暴露，回退 `neutral` |
| `pitch` 取值范围 | 文档有 `[-12,12]` 与 `[-100,100]` 两说 | 本轮 pitch 固定 0，回避不确定性 |
| hd 是否有专属新旁白音色 | Speech 2.8 引入新预设角色，搜索未给确切 id | 首轮候选以已知 id 为主；选定不满意再扩候选清单重跑 preview |

## 参考来源

- [MiniMax 官方音色库（在线试听）](https://www.minimaxi.com/audio/voices)
- [系统音色列表](https://platform.minimaxi.com/docs/faq/system-voice-id)
- [T2A HTTP API 文档](https://platform.minimaxi.com/docs/api-reference/speech-t2a-http)
- [Speech 2.8 介绍](https://www.minimaxi.com/news/minimax-speech-28)

## 中长期：本地音色库（当预设判定不通过时）

若判定实验在 MiniMax 预设里找不到满意的纪录片音色，转入本地自主路线（独立 epic，BACKLOG E8，不在本设计实现范围内）：

- **本地 TTS provider**：CosyVoice 2 一类（中文强、零样本克隆、与在用的 DashScope 同属阿里系、3090 可跑、与 Demucs 错峰用卡）。架构上新增 `providers/cosyvoice_tts.py`，复用现有 provider 模式与 `VoicePreset` 抽象。
- **本地参考音频库**：本地维护一组喜欢的纪录片旁白参考样本，按需克隆成自定义音色——这才是真正的「本地音色库」。
- **前提**：修订 PRD「❌ 音色克隆」约束（自用 + 预设不满足为合理依据），并显式确认参考音频来源合规。
- **已知风险**：克隆「音色像、韵律弱」，而纪录片旁白最吃韵律与情感，可能需配合文本层情绪标记 / 后续微调，质量需单独验收。

## 后续

本设计完成、固化 `nature` 后，同一 `preview-voices` 命令可直接用于 BACKLOG E3 剩余的 `food`/`science`/`history` 预设试听固化。
