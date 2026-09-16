# CARD-01: Document Intelligence Layer（文档智能层）

| 属性 | 值 |
|---|---|
| 优先级 | P0 |
| 竞赛阶段 | 初赛版（9/16–9/22） |
| 对应赛题 | 赛题1 升级为全系统数据入口 |
| 依赖 | 无（首先开工） |
| 实现复杂度 | 高（约 6–8 人日） |
| 状态 | ☐ 未开始 |
| Skill 要求 | 动手前加载 financial-data-provenance |

## 1. 目标

新建 `src/cn/documents/`：统一接管全部真实金融材料的摄入。任何 PDF/TXT/MD/Excel/CSV 进入系统即注册、解析、定位，产出带页码/坐标的结构化事实，支撑"从报告数字反向跳回原始 PDF 页"——本系统最重要的现场展示能力。

## 2. 对应竞赛评分点

数据准确性（解析源头）、来源可核验（page/bbox 定位）、任务完成度（真实输入能力）、现场展示（点击跳转）。

## 3. 为什么需要这个模块

v2 方案的 fatal gap：系统只吃 synthetic 快照，无法处理真实年报。竞赛要求"处理真实金融材料"，且"数据来源可核验"的最强形态就是数字→PDF 页的反向定位。此层是主链第一步，CARD-02/05/06/09/12 全部依赖它。

## 4. 输入 / 输出

- **输入**：文件字节流 + 声明的 document_type；支持类型：年报 PDF、半年报 PDF、季报 PDF、公司公告 PDF、研报草稿 PDF、TXT/Markdown、Excel、CSV
- **输出**：`DocumentRecord`（注册表记录）+ `list[ExtractedFact]`（带定位的结构化事实）+ 解析事件日志

## 5. 数据模型

```python
@dataclass
class DocumentRecord:
    document_id: str        # 内部生成（uuid 或内容寻址）
    sha256: str             # 文件指纹，重复上传去重依据
    filename: str
    source: str             # 用户上传 / 数据目录 / 管理员导入
    document_type: str      # annual | interim | quarterly | announcement | report_draft | other
    company: str | None     # 尽力提取（标题/封面页规则）
    report_period: str | None
    publication_date: str | None
    ingested_at: str
    parser_name: str
    parser_version: str
    page_count: int | None

@dataclass
class ExtractedFact:
    document_id: str
    page: int | None
    bbox: tuple | None     # (x0, y0, x1, y1)，文本型可为 None
    section: str | None    # 章节标题
    table: str | None      # 表格标识
    row: int | None
    column: int | None
    raw_text: str          # 原文切片（供人工复核）
    raw_value: str | None  # 原始数值字符串
    normalized_value: float | None   # 由 CARD-02 完成，本卡可暂空
    currency: str | None
    unit: str | None
    period: str | None
    scope: str | None      # 合并 | 母公司
    available_at: str | None
```

## 6. API / Tool Contract

```python
# src/cn/documents/registry.py
class DocumentRegistry:
    """SQLite（data/documents/registry.db，gitignore）。"""
    def ingest(self, path_or_bytes, declared_type) -> DocumentRecord: ...
    def get(self, document_id) -> DocumentRecord: ...
    def find_by_sha256(self, sha256) -> DocumentRecord | None: ...
    def list(self, document_type=None, company=None) -> list[DocumentRecord]: ...

# src/cn/documents/parsers/
class PDFTextParser: ...      # pdfplumber 文本+页码+bbox
class TableParser: ...        # pdfplumber 表格 → 行列坐标
class OCRFallback: ...        # 文本层为空时触发；未安装 MinerU/PaddleOCR → 返回 error 信封
class FinancialStatementParser: ...  # 三大表识别（表头规则匹配）
class AnnouncementParser: ...       # 公告：标题/日期/关键段
class ReportDraftParser: ...        # 研报草稿：全文段落+页码（供 CARD-05/06）
```

Agent 工具 `IngestCnDocumentTool`（cn_tools.py）：入参 `document_id 或路径`；出参 `status / document / fact_count / parse_summary`。解析失败 → `status: error` + error_code，**绝不静默跳过**。

## 7. 金融逻辑

- 财务三大表识别用表头关键词规则（"合并资产负债表"/"合并利润表"/"合并现金流量表"…），识别失败 → document 标记 `partial`，不猜测
- 研报草稿解析只做分段定位，不做任何判断（判断属于 CARD-05）
- 事实的 available_at 默认 = 文档 publication_date（无则 ingest 时间并标注 degraded）

## 8. Edge Cases

1. 扫描件（文本层为空）→ OCRFallback；OCR 不可用 → 该页标记 failed，facts 不含该页，文档状态 partial
2. 加密/损坏 PDF → 整文档 error，不入注册表
3. 声明类型与内容不符（声明年报实为公告）→ 解析器按内容重新判定并记录偏差警告
4. 同一文件重复上传 → sha256 去重，返回已有 document_id
5. 超大文件（>200MB）→ 拒绝并提示
6. 合并/母公司双表并存 → 两套 facts 分别标注 scope
7. **多页表合并**（v3.0 原方案盲区，角色 H6 点）：A 股年报三大表常跨 2–4 页，每页重复表头、后续页续列。TableParser 必须实现：①表头关键词匹配（"合并利润表"/"合并现金流量表"/"合并资产负债表"）识别表首页；②"续表"/"续"标记识别后续页；③后续页首行跳过（重复表头）；④行列坐标按首页+页偏移统一 → 合成一张完整逻辑表。**这是本卡最大工程量**（至少 1 人日），不得后置。
8. **双列表拆分**（v3.0 原方案盲区）：年报"主要会计数据和财务指标"摘要表常含"本报告期 / 年初至本报告期末"双列。TableParser 输出时标注列名与含义供 CARD-02 的 `detect_period_kind` 判定。
9. **Real 集版式多样性**（v3.0 原方案盲区）：Real 集至少 5 家公司——Demo 用 1 家（提前调试）、演练 2 家、Holdout 2 家（版式差异大：IPO 公司图表化排版、老公司纯文本、不同审计师不同排版）。**单家版式过拟合是致命风险**，必须在 10/16–10/18 冻结窗口做"陌生公司演练"。

## 9. Failure Mode

fail-closed：解析失败的事实不存在，而不是存在但错误。每页解析结果带 `status: ok|partial|failed`。汇总时 failed 页比例 > 阈值 → 文档整体降级为"仅供参考，不可作为事实来源"。

## 10. Validator Rules

- ExtractedFact 无 document_id/page → 拒绝入库
- raw_text 与 normalized 后文本不一致 → 保留 raw_text 原样，禁止覆盖
- 文档 sha256 与注册表不符 → 全部 facts 失效（防篡改）

## 11. Unit Tests

`tests/test_cn_documents.py`：注册/去重/查询；合成 PDF（脚本生成，含表格）解析出预期 facts；bbox 非空；扫描页降级；加密文件 error；sha256 篡改检测。

## 12. Integration Tests

- 端到端：ingest → facts → evidence 账本（复用现有 evidence.py 登记）→ 反查 page
- 与 CARD-11 合成文档集联合跑提取 P/R/F1

## 13. Benchmark

`tests/fixtures/documents/` 合成样例（年报/公告/研报草稿各 ≥3 份，含缺失字段与扫描页样例），生成脚本入库保证可复现。提取 P/R/F1 指标接入 CARD-11，**目标值待 baseline 后冻结**。

## 14. Demo Method

上传真实年报 PDF → 解析进度 → 结构化事实表（带页码列）→ 点击任一数字跳转该 PDF 页（Streamlit 内嵌 PDF 预览 + bbox 高亮，若高亮成本高则页级跳转即可，不为此引入重前端）。

## 15. 验收标准

- [ ] 8 类输入格式全部可 ingest（OCR 类允许 partial）
- [ ] 合成样例集提取的字段级 P/R/F1 有基线数字（不虚构目标值）
- [ ] 反向跳转链路打通：fact → document_id → page 在 UI 可点击
- [ ] 全部测试离线通过；真实 PDF 存 `data/documents/`（gitignore）

## 16. 执行备注（agent 填写）

| 日期 | 记录 |
|---|---|
|  |  |
