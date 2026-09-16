# CARD-15: MCP Server

| 属性 | 值 |
|---|---|
| 阶段 / 优先级 | 阶段4 / P1 |
| 对应选题 | 无（竞赛源代码模块清单点名的 "MCP"） |
| 依赖 | CARD-04/05/06（工具面足够丰富后包装才有演示价值） |
| 状态 | ☐ 未开始 |

## 1. 目标

新建 `src/mcp_server/`：把自有 A 股投研工具面（`cn_tools.py` 注册表）暴露为标准 **Model Context Protocol** 服务（stdio 传输），外部 MCP 客户端（TRAE / Claude Desktop 等）可直接调用本项目工具做 A 股研究。**只做服务端，不做客户端**——守住封闭数据环境。

## 2. 价值主张

- 竞赛模块清单点名 MCP，源代码里真实落地而非 PPT 概念
- 答辩演示杀手锏：现场用外部智能体（评委可自带）通过 MCP 调用本项目工具，展示互操作性——"我们的投研能力是可被生态复用的服务"
- 工具契约不重写：MCP 层是薄封装，schema 与信封直接复用，保证两套入口行为一致

## 3. 设计

### 3.1 依赖

官方 `mcp` Python SDK（MIT，含 FastMCP）。登记第三方清单：Model Context Protocol（Anthropic 主导的开放标准）、mcp SDK（MIT、版本固定）。

### 3.2 服务实现

```python
# src/mcp_server/server.py
from mcp.server.fastmcp import FastMCP

def build_server(tool_registry, snapshot_root) -> FastMCP:
    """遍历 cn_tools 注册表：
    - 每个 Agent 工具 → 一个 MCP tool（name/description/inputSchema 一比一映射）
    - 工具执行结果信封原样透传（status/ok|error 契约不变）
    - snapshot_root 从环境变量读取，缺省指向项目 data/snapshots/cn
    """

# src/mcp_server/__main__.py
"""python -m src.mcp_server 启动 stdio 服务。"""
```

要点：
- 工具白名单机制：默认暴露只读研究工具；写入类/任务类工具不注册
- 每次调用记录结构化日志（工具名/耗时/信封状态）到既有日志体系——MCP 入口的调用同样可追溯
- 不引入任何出站连接：server 只读本地快照

### 3.3 测试（离线）

`tests/test_cn_mcp_server.py`：使用 mcp SDK 的 in-process client session：

1. `list_tools` 返回与注册表白名单一致
2. 调用一个快照型工具（如财务数据）端到端往返，信封字段完整
3. 快照缺失场景返回 error 信封（不崩溃）
4. 白名单外的任务类工具确实未暴露

### 3.4 演示配置（文档交付物）

提供外部客户端接入配置样例（写在使用说明，不入核心代码）：

```json
{ "mcpServers": { "fintrace-cn": { "command": "python", "args": ["-m", "src.mcp_server"] } } }
```

## 4. 实施步骤

1. `pip` 安装并固定 mcp SDK 版本；登记第三方清单。
2. 实现 `server.py` 注册循环 + 白名单 + 日志钩子；`__main__.py` 启动入口。
3. 离线测试四件套（3.3）。
4. 手动验证：外部 MCP 客户端接入调用一个工具成功（截图存执行备注，答辩素材）。
5. 使用说明补 MCP 章节（启动命令/配置样例/白名单说明）。

## 5. 验收标准

- [ ] in-process 测试四项全过，全部离线
- [ ] 工具 schema 与 `cn_tools.py` 注册表一致（一致性测试断言）
- [ ] MCP 入口调用产生与其他入口同构的轨迹/日志记录
- [ ] 外部客户端手动联调成功，配置样例写入使用说明
- [ ] 全部测试通过

## 6. 红线（本卡特有）

- 只做 server：不得添加任何 client 连接第三方 MCP 服务的代码路径
- 白名单外工具（任务/写入类）不暴露；MCP 层不得绕过信封直接返回裸数据
- 不得在 MCP 配置中嵌入密钥；快照路径走环境变量
- mcp SDK 版本固定并在依赖文件注明许可证

## 7. 执行备注（agent 填写）

| 日期 | 记录（白名单清单 / SDK 版本 / 联调结果） |
|---|---|
|  |  |
