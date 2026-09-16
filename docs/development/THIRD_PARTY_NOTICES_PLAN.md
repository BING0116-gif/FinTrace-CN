# THIRD_PARTY_NOTICES_PLAN.md — 第三方依赖合规计划

> 版本：v3.0 Competition Edition ｜ 2026-09-16
> 本文是**计划**而非最终声明。竞赛提交（计划书、复现包、答辩材料）前，必须按 §3 核实流程逐项复核全部依赖的许可证与版本，生成最终 `THIRD_PARTY_NOTICES.md`。**在此之前，本文所有 License 栏均标注"待核实"，不以训练记忆或旧文档中的许可证描述为准。**

---

## 1. 目的与红线

1. 竞赛要求作品可复现、来源可核验——依赖合规是"来源可核验"在工程侧的延伸。
2. 红线：
   - **任何第三方代码不得被描述为自主开发**（计划书、答辩、文档一律禁止）。
   - **不得复制旧文档中未经核实的许可证信息**；每项以提交时官方源（PyPI / 项目仓库 LICENSE 文件）为准。
   - **AGPL 类传染性许可必须隔离为可选依赖**，不进入默认安装路径。
   - 付费数据（tushare 积分接口等）不入提交包，仅本地 `.env` 凭证使用。

## 2. 登记模板（最终 NOTICES 逐项填写）

| 字段 | 说明 |
|---|---|
| 项目名 / 版本 | 锁定 requirements.txt 中精确版本 |
| 来源 | PyPI / 官方仓库 URL |
| License | **以官方源核实后填写**（含核实日期） |
| 是否修改 | 默认"否"；任何 patch 必须单独声明 |
| 具体用途 | 在 FinTrace-CN 中做什么 |
| 调用方式 | import 关系 / CLI / 可选 extras |

## 3. 核实流程（提交前一次性完成）

1. `pip freeze` 与 requirements.txt 比对，确认无未登记的传递依赖进入提交范围（仅登记直接依赖 + 明确影响运行的关键传递依赖）。
2. 逐项打开 PyPI 项目页 / 官方仓库 LICENSE 文件，抄录许可证名称与版本对应关系，记录核实日期与 URL。
3. 检查各许可证的归属声明要求（BSD/MIT 类需保留版权声明；Apache-2.0 需保留 NOTICE）。
4. 用 `python -m pytest -q -m "not integration" -p no:cacheprovider` 验证锁定版本下离线测试全绿。
5. 生成 `THIRD_PARTY_NOTICES.md` 随复现包提交。

## 4. 当前直接依赖登记表（License 待核实）

### 4.1 运行时依赖（requirements.txt）

| 项目 | 版本 | 来源 | License | 修改 | 用途 | 调用方式 |
|---|---|---|---|---|---|---|
| openai | 3.3.0 | PyPI | 待核实 | 否 | LLM provider 客户端（src/llms/） | import |
| anthropic | 0.123.0 | PyPI | 待核实 | 否 | LLM provider 客户端（src/llms/） | import |
| pandas | 3.0.5 | PyPI | 待核实 | 否 | 财务表格/时序数据处理 | import |
| tushare | 1.4.29 | PyPI | 待核实 | 否 | A 股行情/财务 snapshot provider | provider 适配层 |
| akshare | 1.18.92 | PyPI | 待核实 | 否 | A 股公开数据备用 provider | provider 适配层 |
| python-dotenv | 1.2.2 | PyPI | 待核实 | 否 | 本地 `.env` 凭证加载 | import |
| pydantic | 2.13.4 | PyPI | 待核实 | 否 | 数据模型校验（Evidence/Claim/Manifest） | import |
| fastapi | 0.141.1 | PyPI | 待核实 | 否 | versioned research API（api.py） | import |
| uvicorn | 0.52.4 | PyPI | 待核实 | 否 | ASGI server | CLI |
| streamlit | 1.61.1 | PyPI | 待核实 | 否 | workbench 演示界面（workbench.py） | import |
| plotly | 6.9.0 | PyPI | 待核实 | 否 | 图表渲染 | import |

### 4.2 开发/测试依赖（requirements-dev.txt）

| 项目 | 版本 | 来源 | License | 修改 | 用途 | 调用方式 |
|---|---|---|---|---|---|---|
| pytest | 9.1.1 | PyPI | 待核实 | 否 | 离线单元/契约/golden/API 测试 | CLI |
| pytest-asyncio | 1.4.0 | PyPI | 待核实 | 否 | 异步用例支持 | pytest 插件 |
| httpx | 0.28.1 | PyPI | 待核实 | 否 | FastAPI TestClient 传输 | import |

### 4.3 标准库（非第三方，无需登记，列出以澄清边界）

`sqlite3`（runs/manifest 存储）、`hashlib`（document sha256）、`zipfile`（Evidence Pack 打包）、`json`/`jsonl`、`argparse`。

## 5. 计划引入依赖（引入前必须先核实并更新本表）

| 项目 | 计划用途 | 引入卡片 | 合规要点 |
|---|---|---|---|
| pdfplumber | PDF 文本/表格解析（page + bbox 定位） | CARD-01 | 引入前核实当前许可证与版本并登记 |
| jieba | 中文分词（自研 BM25 检索用） | CARD-06 | 同上；分词器不得宣传为自研算法 |
| openpyxl 或 xlsxwriter | Evidence Pack 中 financials/valuation/corrections .xlsx 导出 | CARD-12 | 二选一，核实许可证后锁定 |

## 6. 可选依赖（默认不安装，明确隔离）

| 项目 | 计划用途 | 合规要点 |
|---|---|---|
| MinerU | 复杂版式 PDF 结构化（可选 parser 后端） | **已知风险：AGPL 类传染性许可需以提交时官方源复核为准**；必须 extras 可选安装（`pip install fintrace[mineru]` 式隔离），不进入默认路径，且不得链接其闭源在线服务 |
| PaddleOCR | 扫描件 OCR（可选） | 同上，可选安装 + 许可证核实 |

## 7. 非代码资产合规

| 资产 | 处理 |
|---|---|
| 真实年报/公告 PDF、研报 | 存 `data/`（gitignore）不入库不入提交包；演示与 benchmark 使用时在文档中注明出处与下载日期 |
| 行情 snapshot | 登记来源与 as-of 日期；第三方数据版权归数据源，报告中只作引用 |
| LLM 输出 | 报告中标注模型/版本/温度（Run Manifest 承载），不冒充人工分析 |

## 8. 验收

- [ ] 提交前生成最终 `THIRD_PARTY_NOTICES.md`，每项含核实 URL 与日期
- [ ] AGPL 类依赖（如保留 MinerU）仅存在于可选 extras，默认 `pip install -r requirements.txt` 不安装
- [ ] 计划书技术描述中无任何第三方能力被表述为自主开发
- [ ] `pip freeze` 与登记表交叉核对无遗漏
