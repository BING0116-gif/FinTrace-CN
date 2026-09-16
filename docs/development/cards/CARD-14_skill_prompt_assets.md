# CARD-14: Skill 与 Prompt 资产系统

| 属性 | 值 |
|---|---|
| 阶段 / 优先级 | 阶段3 / P0 |
| 对应选题 | 无（竞赛源代码模块清单点名的 "Prompt" 与 "Skill"） |
| 依赖 | 无硬依赖（Skill 定义引用 CARD-04~06 工具时建议先完成对应卡） |
| 状态 | ☐ 未开始 |

## 1. 目标

建立统一的 Agent 资产注册表：**Skill 库**（按任务路由加载的过程性知识，markdown 资产）+ **Prompt 注册表**（版本化、可指纹的提示词模板），替换散落在 `research_agent.py` 等处的硬编码字符串。让评审在源代码里直接看到 "Skill" 与 "Prompt" 两个被竞赛点名的核心模块，且是工程化管理而非裸字符串。

## 2. 设计

### 2.1 Prompt 注册表（`src/agents/prompts/`）

```python
# registry.py
@dataclass
class PromptSpec:
    prompt_id: str          # 如 "cn_react_system"
    version: int
    template: str           # 模板文件内容，str.format 风格变量
    variables: list[str]
    content_hash: str       # sha256，参与运行指纹

def load_registry(templates_dir: str) -> dict[str, PromptSpec]: ...
def render(prompt_id: str, **variables) -> str: ...   # 缺变量/多余变量均抛错
```

- 模板文件：`src/agents/prompts/templates/*.md`，文件头 frontmatter 声明 id/version/variables。
- 迁移范围：`research_agent.py`、`report.py`、后续 `multiagent/` 中所有 LLM 提示词。**迁移必须语义保持**：先迁移 1 个跑 golden 回归，再批量。
- 运行指纹：扩展现有 benchmark fingerprint（已含 prompt hash 机制的沿用其位置），Skill hash 一并纳入。

### 2.2 Skill 库（`src/agents/skills/`）

```text
src/agents/skills/
├── loader.py               # 解析 + 路由 + 注入
└── library/
    ├── trend-analysis/SKILL.md
    ├── valuation-analysis/SKILL.md
    ├── report-checking/SKILL.md
    ├── memo-writing/SKILL.md
    └── industry-chain/SKILL.md
```

SKILL.md 格式（frontmatter + 正文）：

```markdown
---
name: valuation-analysis
description: A股估值分析标准流程（DCF + 相对估值三角验证）
triggers: [估值, DCF, 值多少钱, 目标价, 合理价格]
required_tools: [RunCnDcfValuationTool]      # 引用注册表中现有工具名
version: 1
---
## 流程
1. 先取快照财务与价格（证据挂账）…
2. 运行 DCF 并核对假设 provenance…
## 边界规则
- 假设参数必须区分 sourced 与 assumption …
- 输出必须含适用边界声明 …
```

```python
# loader.py
@dataclass
class SkillSpec:
    name: str
    triggers: list[str]
    required_tools: list[str]
    version: int
    body: str
    content_hash: str

def load_skills(library_dir: str) -> list[SkillSpec]: ...
def match_skill(task_text: str, skills: list[SkillSpec],
                available_tools: set[str]) -> SkillSpec | None:
    """触发词匹配 + required_tools 可用性预检（缺工具 → 该技能不适用并记录原因）。"""

def inject_skill(system_prompt: str, skill: SkillSpec) -> str: ...
```

### 2.3 运行时接入

- 单 Agent 路径：`CnResearchAgent` 开工前 `match_skill` 命中则注入；命中与未命中都写入轨迹（含 skill hash）。
- 多智能体路径：CARD-08 编排器各角色按需加载对应 skill（fundamental→trend-analysis，valuation→valuation-analysis…）。
- 离线模式：skill 照常注入（offline agent 脚本同样消费技能里的流程约束），保证演示形态一致。

## 3. 实施步骤

1. 通读现有 prompt 散布点（`research_agent.py` 等），列迁移清单写入执行备注。
2. 实现 Prompt 注册表 + 模板文件 + 单测（渲染变量校验、hash 稳定性）。
3. 迁移第一个 prompt 并跑 golden 回归（对比迁移前后输出指纹一致或差异可解释）。
4. 批量迁移其余 prompt。
5. 实现 Skill loader + 5 个内置 SKILL.md。
6. Agent 接入 + 轨迹记录。
7. `tests/test_cn_skills.py`：触发词路由、缺工具降级、hash 纳入指纹、离线注入。

## 4. 验收标准

- [ ] 代码库中 LLM 提示词零硬编码散落（全部走注册表，`grep` 断言测试）
- [ ] Prompt 迁移后现有测试与 golden 用例零回归
- [ ] Skill 路由测试：5 技能各自命中、无命中返回 None、缺工具技能不误触发
- [ ] 运行指纹含 skill+prompt hash；同资产运行指纹稳定
- [ ] 全部测试通过

## 5. 红线（本卡特有）

- Skill 是过程性约束，不得成为绕过 gate 或编造事实的通道——skill 正文出现与红线冲突的指令时 loader 拒绝加载（写一个静态检查器扫 library）
- Prompt 迁移逐个进行，禁止一次性全量替换后才发现回归
- Skill 内容版本化，禁止热改正文不留版本号

## 6. 执行备注（agent 填写）

| 日期 | 记录（迁移清单 / 触发词调整 / 偏差） |
|---|---|
|  |  |
