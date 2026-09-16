# CARD-06: Retrieval Engine（检索引擎）

| 属性 | 值 |
|---|---|
| 优先级 | P0 |
| 竞赛阶段 | 初赛版（基础 9/16–9/22，随文档积累增强） |
| 对应赛题 | 竞赛任务链第一环"信息检索"；赛题6 引用素材 |
| 依赖 | CARD-01（文档 chunk 来源） |
| 实现复杂度 | 中（约 3–4 人日） |
| 状态 | ☐ 未开始 |
| Skill 要求 | 动手前加载 financial-data-provenance |

## 1. 目标

新建 `src/cn/retrieval/`：对文档语料（年报 MD&A、公告、研报段落）建立证据化检索。BM25 **自研实现**（确定性优先），可选向量重排（显式 model-dependent）。修正 v2 的关键错误：**chunk ≠ evidence，只有被引用的 chunk 才入账**。

## 2. 对应竞赛评分点

信息检索（任务链第一环）、引用管理（quote/paraphrase/inference 三型）、结果稳定性（同查询同结果）。

## 3. 为什么需要这个模块

竞赛任务描述把"信息检索"列为智能体第一任务；备忘录的"业绩变动原因"需要检索 MD&A 段落做有据引用。市面方案是向量 RAG 黑盒，本项目用"确定性检索优先"对齐可复现主线。

## 4. 输入 / 输出

- **输入**：文档 chunk（CARD-01 解析产物，带 document_id/page/section）+ 查询字符串
- **输出**：`SearchHit[]`（带出处定位与 mode 标注）

## 5. 数据模型

```python
@dataclass
class CorpusChunk:
    chunk_id: str           # 与 evidence_id 严格分离
    document_id: str
    page: int | None
    section: str | None
    text: str

@dataclass
class SearchHit:
    chunk: CorpusChunk
    score: float
    mode: str               # bm25 | hybrid
    rank: int

class Citation(str, Enum):
    quote = "quote"          # 逐字一致，校验器强制
    paraphrase = "paraphrase"  # 允许重述，必须绑定原始 chunk_id
    inference = "inference"    # 允许组合多证据，必须标记
```

## 6. API / Tool Contract

```python
# bm25.py —— 自研，不引第三方 BM25 库
class Bm25Index:
    """k1=1.5, b=0.75（模块顶部常量+依据注释）。jieba 分词（MIT）。
    同索引同查询 → 结果逐项相等（确定性测试）。"""

# 正确的证据流（修正 v2）：
# Document → Chunk → Index → Retrieval → Selected Chunk → Evidence
# 只有真正用于支持 Claim 的 chunk 才调 ledger.register() 生成 evidence_id
def cite_chunk(chunk_id, citation_type, span) -> str: ...
```

Agent 工具 `SearchCnCorpusTool`：入参 `query / top_k`；出参 `status / hits[]`（每 hit 含 text/page/section/document_id，**不含 evidence_id——引用时才生成**）。

## 7. 金融逻辑

- 检索是"定位"不是"生成"：命中文本只能被逐字引用（quote 校验）或显式 paraphrase
- 检索文本中的数字不得直接进入结论——必须走数值校验路径（CARD-02/03）
- 向量重排（可选增强）：走 src/llms 国产 embedding 接口，SQLite 缓存 keyed by (model, text_hash)，未配置凭证自动降级 bm25 并标注 mode

## 8. Edge Cases

1. 空语料 → 空结果 + 明确提示（不报错）
2. 查询无命中 → 返回空列表而非强行近似
3. 同文档多页相似段落 → 各自独立 chunk，靠 page 区分
4. quote 校验失败（报告文本与 chunk 不逐字一致）→ validator 拒绝该引用，降级为需 paraphrase 声明
5. embedding 凭证缺失 → hybrid 自动降 bm25，结果标注 mode=bm25

## 9. Failure Mode

检索失败不影响主链其他环节（独立降级）。向量化失败 → 回退 BM25。**禁止**在降级时假装结果等价——mode 字段如实区分。

## 10. Validator Rules

- quote 型引用：报告文本与 chunk.text 逐字一致（字符级断言）
- paraphrase 型：必须携带 chunk_id 且 chunk 存在
- inference 型：必须标记且 derived_from 非空
- Evidence Ledger 中不存在未被任何 Claim 引用的检索型孤儿证据（账本卫生检查）

## 11. Unit Tests

- BM25 手工算例（5 文档小语料人工算分核对）
- 同查询两次结果逐项相等（确定性）
- quote/paraphrase/inference 校验三路
- 引用后才入账：检索 100 次不产生任何 evidence，引用 1 次产生 1 条

## 12. Integration Tests

CARD-01 文档 → 索引 → 检索 → CARD-10 备忘录引用 → ledger 只含被引用 chunk。

## 13. Benchmark

固定查询集 + 金标段落（合成语料）计算 recall@5；Citation Precision/Recall 接入 CARD-11。目标值待 baseline 后冻结。

## 14. Demo Method

检索页：输入查询 → 命中列表带页码出处；在备忘录中点击引用 → 跳转 chunk → PDF 页。

## 15. 验收标准

- [ ] BM25 自研实现 + 手工算例通过 + 确定性测试通过
- [ ] chunk/evidence 分离机制有测试（检索不污染账本）
- [ ] 引用三型校验全部有测试
- [ ] 未配置 embedding 时自动降级且如实标注
- [ ] 全部测试离线通过

## 16. 执行备注（agent 填写）

| 日期 | 记录 |
|---|---|
|  |  |
