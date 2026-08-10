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
| E7 | 人声/BGM 分离 | P2 |

---

## P1.5 — 核心质量

### E1 翻译地道化
- 优化翻译 prompt：纪录片旁白风格、口语化、孩子能懂。
- 长难段用 `deepseek-reasoner` 兜底。
- 调 `context_window` 平衡一致性与成本。
- **验收**：抽 10 段人耳评，无明显机翻腔/硬译。

### E2 时长对齐
- TTS 后量测 clip 时长。
- 超 段时长 → 调 `speed` 重合成 → 再 prompt 精简 → 拉伸兜底。
- **验收**：clip 溢出率 = 0；无段间叠音。

### E3 音色固化
- `dub voices` 校验有效 voice_id。
- 试听候选，固化为自然纪录片男/女声。
- **验收**：`voices.yaml` 全部为已验证音色。

### E4 测试与稳定性
- 核心纯函数单测：`config_signature`、`input_hash`、时长校验、mix 时序、Segment 序列化。
- provider 契约测试（录制响应锁字段）。
- CI：lint + 单测；确认 OSS 失败路径对象回收。
- **验收**：核心覆盖 ≥ 70%；main 持续绿。

---

## P2 — 增强

### E5 人工校对回路
- `dub export` 导出可编辑译文；`dub zh --edits <file>` 读回，跳过翻译直接 TTS。
- **验收**：改译后重跑只触发 TTS 及之后阶段。

### E6 术语表
- `config/glossary.yaml`：物种/人名/地名；注入 prompt 强制一致。

### E7 人声/BGM 分离
- 远程 Demucs v4 分离；中文段 ducking；本地无 GPU 降级回整体衰减。
- **验收**：中文段无英文人声残留。

---

## 不做

SaaS / Web UI、音色克隆、大规模分发。

## 里程碑

- **M1（P1.5）**：E1+E2+E3+E4 → 翻译地道、配音自然、可维护。
- **M2（P2）**：E5+E6+E7 → 质量再提一档。
