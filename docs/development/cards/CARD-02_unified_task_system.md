# CARD-02: 统一任务系统

| 属性 | 值 |
|---|---|
| 阶段 / 优先级 | 阶段0 / P0 |
| 对应选题 | 无（工程基建，竞赛"执行过程可追溯"的直接支撑） |
| 依赖 | CARD-01（页面已拆分，接入点清晰） |
| 状态 | ☐ 未开始 |

## 1. 目标

把现有两套任务生命周期（`workbench_service.py` 的 service 任务与 `agent_service.py` 的 agent 任务）统一为单一 SQLite 持久化任务系统：重启不丢历史、状态机规范、事件轨迹完整。

## 2. 背景与现状

- `src/cn/workbench_service.py`：`ThreadPoolExecutor(max_workers=2)` + 散落 JSON 文件存储任务 + 进程内字典跟踪运行态；重启后运行态丢失。
- `src/cn/agent_service.py`：agent 研究任务另一套生命周期与存储。
- 双系统概念割裂，是"demo 感"和"乱"的第二来源。
- 竞赛要求"完整记录文件访问、工具调用、计算过程和结果生成情况"——统一任务轨迹是硬需求。

## 3. 设计

### 3.1 存储：`src/cn/task_store.py`（新建）

```python
from enum import Enum

class TaskStatus(str, Enum):
    queued = "queued"
    running = "running"
    done = "done"
    failed = "failed"
    cancelled = "cancelled"

class TaskKind(str, Enum):        # 与现状对齐后可增删
    research = "research"         # agent 研究
    daily_review = "daily_review" # 每日复盘（现有）
    valuation = "valuation"      # 后续卡片新增 kind 在此登记

@dataclass
class TaskRecord:
    task_id: str
    kind: str
    params: dict
    status: str
    created_at: str
    started_at: str | None
    finished_at: str | None
    result: dict | None
    error: str | None

class TaskStore:
    """SQLite(WAL) 持久化任务表。库文件 data/tasks.db（data/ 不入 Git，运行时自建）。"""
    def create(self, kind, params) -> TaskRecord: ...
    def mark_running(self, task_id) -> None: ...
    def finish(self, task_id, result: dict | None, error: str | None) -> None: ...
    def append_event(self, task_id, event: dict) -> None: ...   # 事件流水（工具调用/进度）
    def get(self, task_id) -> TaskRecord: ...
    def list(self, kind=None, status=None, limit=100) -> list[TaskRecord]: ...
    def recover_interrupted(self) -> int:
        """启动时调用：把 running 状态的任务标记为 failed(error='interrupted by restart')，返回数量。"""
```

### 3.2 服务合并：`src/cn/task_service.py`（新建）

- 以 `workbench_service.py` 现有执行器为基础（保留有界线程池与超时控制），替换其 JSON 存储为 `TaskStore`。
- `agent_service.py` 的任务注册迁移到同一 `TaskKind` 体系；对外函数签名尽量保持，减少 workbench 页面改动。
- 旧 JSON 任务文件提供一次性只读迁移（读到 SQLite 后归档），迁移函数带开关，默认关闭。

### 3.3 接入

- `api.py` 与 `workbench/pages/` 中所有任务列表/详情读取改为走 `TaskStore`。
- 任务发起保持现有入口不变（页面/接口零语义变化）。

## 4. 实施步骤

1. 写 `task_store.py` + 单测（建表/状态流转/事件追加/中断恢复，全部用 tmp_path，不碰真实 data/）。
2. 写 `task_service.py` 合并两套执行入口；先在测试里用假任务函数验证状态机。
3. 迁移 `workbench_service.py` 与 `agent_service.py` 调用方；删除被替代的 JSON 存储路径与内存运行态字典。
4. `api.py` 任务端点改读 `TaskStore`，响应字段保持现有 envelope 契约（先读 `api.py` 现有端点再动手，勿破坏既有响应结构）。
5. 更新 `tests/test_cn_workbench_service.py`、`tests/test_agent_research_service.py` 到新存储；冒烟验证。

## 5. 验收标准

- [ ] 单测覆盖状态机全部合法/非法流转（非法流转抛错）
- [ ] 进程重启后任务历史完整保留；重启前 running 的任务被标记为 `failed(interrupted by restart)`
- [ ] service 与 agent 任务在同一列表可见，kind 可区分
- [ ] 全部测试通过；`api.py` 既有端点契约测试不回归
- [ ] SQLite 文件位于 `data/`（确认 `.gitignore` 覆盖）

## 6. 红线（本卡特有）

- 不引入 MongoDB / Redis / Celery / 消息队列中间件
- 线程池保持有界（默认 2 不扩大），避免评审环境资源失控
- 事件记录只追加不修改（审计要求）

## 7. 执行备注（agent 填写）

| 日期 | 记录（偏差 / 迁移映射 / 遗留问题） |
|---|---|
|  |  |
