# CARD-14: Prompt Registry（提示词注册表）

| 属性 | 值 |
|---|---|
| 优先级 | P1 |
| 竞赛阶段 | 初赛起随 LLM 功能落地（CARD-05/10 时同步迁移），10-15 前完成核心 prompt |
| 对应赛题 | 竞赛源代码模块清单点名的 "Prompt" |
| 依赖 | CARD-07（prompt_hash 入 manifest） |
| 实现复杂度 | 低（约 1.5 人日） |
| 状态 | ☐ 未开始 |

## 1. 目标

新建 `src/agents/prompts/`：版本化提示词注册表，记录 prompt_name/version/hash/model/temperature/created_at，替换散落在 `research_agent.py` 等处的硬编码字符串。**Skill 不做空壳**：只有存在真实功能价值（如稳定的多步流程约束）才建，否则只交付 Prompt Registry。

## 2. 对应竞赛评分点

技术要求点名模块、结果可复现（prompt_hash 纳入 manifest）。

## 3. 为什么需要这个模块

源代码清单里 "Prompt" 是点名模块；且 prompt 变更无版本 = 复现性破坏。v2 的 Skill 库设计有"为名词而建"的倾向，本卡收敛。

## 4. 输入 / 输出

- **输入**：现有代码中的 prompt 字符串 + 新卡片（05/10）的 prompt 需求
- **输出**：注册表 + 模板文件 + hash 服务

## 5. 数据模型

```python
@dataclass
class PromptSpec:
    prompt_name: str
    prompt_version: int
    template: str
    variables: list[str]
    prompt_hash: str          # sha256
    model: str | None          # 使用时记录
    temperature: float | None
    created_at: str
```

## 6. API / Tool Contract

```python
def load_registry(templates_dir) -> dict[str, PromptSpec]: ...
def render(prompt_name, **variables) -> str: ...   # 缺/多变量抛错
def record_usage(prompt_name, model, temperature) -> None: ...
```

模板文件：`src/agents/prompts/templates/*.md`，frontmatter 声明 name/version/variables。

## 7. 金融逻辑

无直接金融逻辑；但 prompt 内容迁移**语义必须保持**：先迁 1 个跑 golden 回归，再批量。CARD-05 提取器与 CARD-10 叙述段 prompt 是本卡首批登记对象。

## 8. Edge Cases

1. 同名不同版本并存 → 注册表按 (name, version) 寻址，运行记录实际使用版本
2. 模板变量缺失 → 渲染抛错（禁止半渲染）
3. Skill 目录决策 → 若无真实价值，在 THIRD_PARTY/答辩材料中如实说明"未采用 Skill 机制及其原因"

## 9. Failure Mode

注册表加载失败 → 任务 fail-closed（不回退硬编码字符串——回退等于绕过版本化）。

## 10. Validator Rules

- 代码库 LLM prompt 零硬编码（grep 断言测试）
- prompt_hash 必须进入 RunManifest（CARD-07 联动断言）
- 版本只增不改（同版本内容变化测试报错）

## 11. Unit Tests

渲染变量校验；hash 稳定性；版本不变性；零硬编码 grep 断言。

## 12. Integration Tests

迁移后现有 agent 测试与 golden 用例零回归；manifest 含 prompt_hash。

## 13. Benchmark

Multi-run Consistency 间接覆盖（prompt 版本化是稳定前提）。

## 14. Demo Method

展示注册表页（name/version/hash 列表）+ manifest 中的 prompt_hash——证明 prompt 可审计。

## 15. 验收标准

- [ ] 零硬编码断言通过；golden 零回归
- [ ] (name, version) 寻址与 hash 入 manifest 打通
- [ ] Skill 取舍决策有明确记录（做或不做均有理由文档化）

## 16. 执行备注（agent 填写）

| 日期 | 记录 |
|---|---|
|  |  |
