# CARD-16: 结构化检索引擎（retrieval/）

| 属性 | 值 |
|---|---|
| 阶段 / 优先级 | 阶段3 / P1 |
| 对应选题 | 竞赛任务链第一环"信息检索"；选题2 的"业绩变化原因分析"素材；选题6 备忘录引用 |
| 依赖 | 无硬依赖（CARD-10 备忘录是主要消费方，本卡宜先于它完成） |
| 状态 | ☐ 未开始 |

## 1. 目标

新建 `src/cn/retrieval/`：对公告文本与年报 MD&A 段落建立**证据化语料检索**。基线 BM25 **自研实现**（确定性、零向量库依赖），向量重排作为可选增强层（显式标注 model-dependent）。检索结果永远带出处定位，供 LLM 引用而非生成事实。

## 2. 设计立场（答辩叙事）

市面方案 = 向量 RAG 黑盒。本项目 = **确定性检索优先**：同查询必同结果（可复现），BM25 自研约百行代码（技术深度），向量层只是可选增强且缓存指纹化（诚实分层）。这与全项目"可验证/可追溯/可复现"主线一致。

## 3. 详细设计

### 3.1 语料构建（`src/cn/retrieval/corpus.py`）

```python
@dataclass
class CorpusChunk:
    chunk_id: str
    doc_id: str            # 公告ID / 年报文件ID
    source_type: str       # announcement | mdna | demo_synthetic
    text: str
    coordinates: dict     # {title, section, page?} 出处定位
    evidence_id: str      # 入证据账本，检索即引用

def build_corpus(sources) -> list[CorpusChunk]:
    """分块（段落级，上限512字符），逐块登记证据账本。"""
```

语料来源（三类，全部合规）：
1. live：AkShare 公告接口的标题+摘要（扩展 `src/cn/providers/akshare.py`）
2. 离线演示：合成 MD&A 段落样例（`tests/fixtures/corpus/`，自造文本入库保证可复现）
3. 后续：CARD-11 文档解析产出的公告字段化结果

### 3.2 BM25 自研（`src/cn/retrieval/bm25.py`）

```python
class Bm25Index:
    """k1=1.5, b=0.75 标准参数（模块顶部常量+注释依据）。
    分词：jieba（MIT）。同索引同查询 → 结果列表逐项相等（确定性测试）。"""
    def __init__(self, chunks: list[CorpusChunk]): ...
    def search(self, query: str, top_k: int = 5) -> list[tuple[CorpusChunk, float]]: ...
```

自研不引第三方 BM25 库：实现 IDF/BM25 打分公式本体 + 单测对照手工算例。

### 3.3 可选向量层（`src/cn/retrieval/embedding.py`）

```python
class EmbeddingReranker:
    """可选增强。embedding 走 src/llms 的 provider 客户端（国产模型 embedding 接口）。
    SQLite 缓存 keyed by (model, text_hash)——重跑零成本。
    未配置凭证时模块不可用，hybrid 自动降级 BM25 并标注 mode=bm25。"""
```

### 3.4 混合检索（`src/cn/retrieval/hybrid.py`）

```python
@dataclass
class SearchHit:
    chunk: CorpusChunk
    score: float
    mode: str            # bm25 | hybrid（hybrid=BM25+向量RRF融合）
    rank: int

def search(query, top_k, reranker: EmbeddingReranker | None) -> list[SearchHit]: ...
```

融合用 RRF（Reciprocal Rank Fusion，公式常量注释依据），确定性可测；embedding 路径结果带 model 名标注。

### 3.5 工具注册与消费方

- `SearchCnCorpusTool`（`cn_tools.py`）：入参 `query / top_k`；出参 `status / hits[]`（每 hit 含 text、coordinates、evidence_id、mode）。
- 消费方：
  - CARD-10 备忘录"业绩变动原因"段：检索 MD&A 段落 → LLM 总结时**逐字引用**检索文本并标 evidence_id，不得改写数字
  - CARD-06 纠错：定位草稿陈述的可能原文出处（辅助 source 定位）
  - 独立演示：workbench 检索页（输入 query → 带出处的命中列表）

## 4. 实施步骤

1. jieba 依赖引入（MIT，登记清单）。
2. `corpus.py` + 证据账本对接 + 合成语料 fixture。
3. `bm25.py` 自研实现 + 手工算例单测（构造 5 文档小语料，人工算分核对）+ 确定性测试（两次搜索结果逐项相等）。
4. `hybrid.py` + RRF + 降级路径。
5. `embedding.py` 可选层 + SQLite 缓存 + 离线降级。
6. 工具注册 + workbench 检索页 + 契约测试（ok/降级/空结果三路）。
7. 检索评测：固定查询集 + 金标段落（合成语料构造），recall@5 ≥ 0.8；结果贴执行备注。

## 5. 验收标准

- [ ] BM25 手工算例精确匹配；确定性测试（同查询两次结果完全相等）通过
- [ ] 检索结果 100% 带 evidence_id 与 coordinates；未配置 embedding 时自动降级 bm25 并标注
- [ ] recall@5 ≥ 0.8（合成金标集）；全部测试离线
- [ ] 备忘录消费路径：引用文本与检索原文逐字一致（一致性测试）
- [ ] 全部测试通过

## 6. 红线（本卡特有）

- 检索是"定位"不是"生成"：命中文本只能被逐字引用，LLM 不得改写后被当作原文
- 检索文本中的数字不得直接进入结论，必须走数值校验路径
- 不引入向量数据库/重依赖框架（FAISS/Chroma/LangChain 等一律不用）；SQLite + 自研打分即止
- embedding 层默认关闭，开启时结果带 model 标注，绝不冒充确定性

## 7. 执行备注（agent 填写）

| 日期 | 记录（语料规模 / recall 结果 / 偏差） |
|---|---|
|  |  |
