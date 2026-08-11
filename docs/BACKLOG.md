# Product Backlog — dub

> 围绕「翻译准确地道 + 配音自然 + 孩子能看」排，不扩范围。
>
> 配套 [PRD.md](./PRD.md) · [ARCHITECTURE.md](./ARCHITECTURE.md)

## 总览

| Epic | 主题 | 优先级 |
|---|---|---|
| E1 | 翻译地道化 | **P1.5** |
| E2 | 时长对齐 | **P1.5** |
| E3 | 音色固化 | **P1.5** |
| E4 | 测试与稳定性 | **P1.5** |
| E5 | 人工校对回路 | P2 |
| E6 | 术语表 | P2 |
| E7 | 人声/BGM 分离 | ✅ 已完成 |

---

## P1.5 — 核心质量

### E1 翻译地道化
- 优化翻译 prompt：纪录片旁白风格、口语化、孩子能懂。
- 长难段用 `deepseek-reasoner` 兜底。
- 调 `context_window` 平衡一致性与成本。
- **验收**：抽 10 段人耳评，无明显机翻腔/硬译。

### E2 时长对齐
- ✅ TTS 后量测 clip 时长并校验窗口（`dub.timing`）。
- ✅ 自动修复三级阶梯（`dub.remediate`）：① 翻译期字数预算重译 → ② speed 重合成（≤`tts.max_speed`）→ ③ ffmpeg `atempo` 保音高精确对齐；退化短窗截断。已接入 translate/pipeline。
- ⬜ live 实跑验证（MiniMax speed 时长反比、DeepSeek 硬预算）——测试已写（`@pytest.mark.live`），待 `--run-live` 真实 key 确认。
- **验收**：clip 溢出率 = 0（退化段除外）；无段间叠音。

### E3 音色固化
- ✅ `nature` 固化为 `male-qn-yuanbo`（渊博男声）+ `language_boost=Chinese`/`emotion=neutral`。
- ⬜ `food`/`science`/`history` 试听候选并固化。
- **验收**：`voices.yaml` 全部为已验证音色。

### E4 测试与稳定性
- ✅ 核心纯函数单测：`config_signature`（含 voice 预设）、`input_hash`、时长校验、`Segment` 序列化、`Cache`。快车道 33 测试全绿，`cache/models/timing` 100% 覆盖；`@pytest.mark.live` 门控已就位。
- ⬜ mix 时序测试（依赖 pydub）。
- ⬜ provider 契约测试（录制响应锁字段）。
- ⬜ CI：lint + 单测；确认 OSS 失败路径对象回收。
- **验收**：核心覆盖 ≥ 70%；main 持续绿。

---

## P2 — 增强

### E5 人工校对回路
- `dub export` 导出可编辑译文；`dub zh --edits <file>` 读回，跳过翻译直接 TTS。
- **验收**：改译后重跑只触发 TTS 及之后阶段。

### E6 术语表
- `config/glossary.yaml`：物种/人名/地名；注入 prompt 强制一致。

### E7 人声/BGM 分离 ✅
- ✅ 本地 Demucs `two_stems=vocals` 出伴奏（原计划远程 AutoDL；本机有 3090，改本地，免端点）。
- ✅ mix 句间 ducking（`duck_db`）；未装 Demucs / 分离失败时降级回整体衰减（HQ 底）。
- ✅ 验收：中文段无英文人声残留（`dub zh --sample N` 人耳验）。

---

## 不做

SaaS / Web UI、音色克隆、大规模分发。

## 里程碑

- **M1（P1.5）**：E1+E2+E3+E4 → 翻译地道、配音自然、可维护。
- **M2（P2）**：E5+E6+E7 → 质量再提一档。（E7 已提前完成并落地）
