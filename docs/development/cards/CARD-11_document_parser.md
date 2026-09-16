# CARD-11: 公告文档结构化提取（document_parser/）

| 属性 | 值 |
|---|---|
| 阶段 / 优先级 | 阶段4 / P2 |
| 对应选题 | 选题1 数据结构化提取 |
| 依赖 | 无硬依赖（建议在 CARD-03 后做，快照接入顺畅） |
| 状态 | ☐ 未开始 |

## 1. 目标

新建 `src/cn/document_parser/`：从公告 PDF 提取质押、中标、股权变动三类关键字的**规定 schema** 结构化输出，输出结果作为事实挂证据账本进入快照体系。基线 pdfplumber（MIT），扫描件增强 MinerU（AGPL-3.0，**可选依赖**）。

## 2. 竞赛考察点映射

| 选题1考察点 | 本卡落点 |
|---|---|
| 字段提取完整性 | 三类公告 schema + 必填字段校验 |
| 格式规范性 | 输出即 schema，带 evidence_id/as_of |
| 表格解析准确性 | pdfplumber 表格抽取 + 合成样例 F1 评测 |
| 结果一致性 | 同输入重复解析结果哈希一致（确定性断言） |

## 3. 详细设计

### 3.1 目录与 schema

```text
src/cn/document_parser/
├── __init__.py
├── pdf_extractor.py     # pdfplumber 文本/表格抽取封装
├── pledge.py            # 质押公告 → PledgeRecord
├── tender_won.py        # 中标公告 → TenderRecord
├── share_change.py      # 股权变动公告 → ShareChangeRecord
└── schemas.py           # 三类 dataclass + 必填字段定义
```

```python
@dataclass
class PledgeRecord:
    pledgor: str            # 出质人
    pledgee: str            # 质权人
    shares: float | None    # 质押股数
    ratio: float | None     # 占总股本比例
    announcement_date: str | None
    source_file: str        # 证据定位（文件+页码）
    missing_fields: list[str]  # 必填未提取到的字段显式列出，绝不编造

# TenderRecord: 公司/甲方/中标金额/项目名/日期
# ShareChangeRecord: 股东/变动方向/变动数量/变动后持股/比例
```

### 3.2 提取纪律

- 规则优先：正则 + 表格单元格坐标规则；LLM 仅允许做"字段候选定位"的辅助，**最终值必须来自文本/表格原文切片**，且切片随记录保存（可人工复核）。
- 必填字段提取失败 → `missing_fields` 显式登记，字段值保持 None；禁止 LLM 补全。
- 输出统一信封：`status: ok | partial | error`（partial = 有 missing_fields）。

### 3.3 评测集（合规红线）

**不使用真实公告 PDF 入库**（版权）。`tests/fixtures/announcements/` 用脚本生成三类**合成公告**（自造文本+pdfplumber 可解析的表格结构，生成脚本一并入库保证可复现）。字段真值由生成脚本写入 fixture 元数据，F1 自动计算。

### 3.4 可选 MinerU 增强

- 依赖声明放 `pyproject.toml`（若仓库无则按现有依赖管理方式）extras 组：`[project.optional-dependencies] mineru = [...]`，默认不安装。
- MinerU 路径仅在 `pdfplumber` 文本抽取失败（扫描件特征：文本层为空）时启用。
- 第三方清单登记：MinerU, AGPL-3.0, 可选依赖, 扫描件增强。

## 4. 实施步骤

1. 写合成公告生成脚本（三类各 ≥3 份，含 1 份字段缺失样例）。
2. 实现 `pdf_extractor.py` + 三类解析器（规则版）。
3. 评测：字段级 precision/recall/F1；结果一致性哈希测试。
4. MinerU 可选路径 + 未安装时优雅降级。
5. 工具 `ParseCnAnnouncementTool`（`cn_tools.py`）+ 契约测试（ok/partial/error 三路）。
6. `tests/test_cn_document_parser.py` 全离线。

## 5. 验收标准

- [ ] 三类合成公告字段 F1 ≥ 0.9；缺失样例正确返回 partial + missing_fields
- [ ] 同输入两次解析输出哈希一致
- [ ] pdfplumber 失败 → 扫描件路径降级逻辑有测试（MinerU 未安装时 error 信封，不崩溃）
- [ ] 全部测试通过；`pip install .` 默认不含 MinerU

## 6. 红线（本卡特有）

- 真实公告 PDF 与其原文不得入 Git/提交；样例一律合成
- LLM 不得成为字段值的最终来源；每个字段保留原文切片供复核
- AGPL 代码隔离：MinerU 调用仅限可选入口，核心代码路径零 AGPL 污染

## 7. 执行备注（agent 填写）

| 日期 | 记录（生成脚本设计 / F1 结果 / 偏差） |
|---|---|
|  |  |
