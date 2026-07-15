# CookQA 未完成事项

- 更新日期：2026-07-15
- 当前状态：P0、P1、Phase 2 已完成；当前定义范围内无未完成工程项
- 目标平台：Windows 本机
- 设计基线：[`docs/superpowers/specs/2026-07-13-cookqa-graph-rag-design.md`](superpowers/specs/2026-07-13-cookqa-graph-rag-design.md)
- P1 计划：[`docs/superpowers/plans/2026-07-14-cookqa-p1-acceptance-implementation.md`](superpowers/plans/2026-07-14-cookqa-p1-acceptance-implementation.md)

## 1. 当前结论

CookQA 已在真实本地 Neo4j Windows 服务、Ollama 与固定 200 道菜索引上完成 P1 验收。当前可以称为“完成 P1 验收的本地 Graph RAG MVP”，但仍不应描述为已经完成生产部署、长期运维或全量质量评估的平台。

固定数据源已核验：

```text
HowToCook HEAD: cbc524e28a88bf5ccc6e094004cfbeba1ea6fdf9
HowToCook status --short: empty
Active recipe count: 200
Embedding model: bge-m3:latest
Embedding dimension: 1024
Neo4j Windows service: Running / Automatic
```

## 2. P1 已完成内容

### 2.1 运行时语义

- 运行时与构建阶段读取同一份 `config/ingredient_aliases.json`。
- “不辣/辣味”等表达使用结构化标签约束，不再伪装成名为“辣”的普通食材。
- “不用某食材”可解析为排除条件。
- 相似菜谱中的参考菜名不再被误解析成必需食材。
- “简单”等缺乏可靠元数据的词不会成为硬难度过滤。
- “凉菜”查询会扩展为菜谱中常见的“凉拌”命名词，但不改变原始问题和硬约束。

### 2.2 相似菜谱检索

- `similar_recipe` 直接复用参考菜谱在活动 FAISS 索引中的向量，不再重新嵌入整句问法。
- 参考菜谱本身不会出现在相似结果中。
- FAISS 可用时保持其相似度顺序；参考无关的 Neo4j 食材数量榜只补充候选和验证约束，不能主导排名。
- 排除食材等硬条件仍在返回前统一验证。

### 2.3 本地模型与 readiness

- 本机 `bge-m3` 冷加载实测超过原来的 0.75 秒，默认 dense 超时已调整为 6 秒。
- 显式卸载模型后的首次预热请求约 2.87 秒，随后恢复到约 0.18–0.20 秒。
- `/ready` 将 `bge-m3` 和 Ollama 标签 `bge-m3:latest` 视为同一模型，不再误报缺失。
- Neo4j、活动 manifest、BM25、FAISS ID 集合和 1024 维向量已完成一致性校验。

### 2.4 安装与打包

- setuptools 包发现已限制为 `api*` 和 `cookqa*`。
- `python -m pip install --no-deps -e ".[dev,faiss]"` 已成功。
- 安装后 `api`、`cookqa` 可导入，`pip check` 无损坏依赖。

## 3. P1 最终验证证据

### 3.1 自动化测试

```text
106 passed, 1 warning in 1.08s
Ruff: All checks passed!
pip check: No broken requirements found.
```

唯一警告来自当前环境的 FastAPI TestClient 兼容层：

```text
StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated
```

### 3.2 真实 HTTP 基准

报告路径：`Data/runtime/benchmark-report.json`（Git 忽略的运行产物）。

```text
case_count: 50
evaluated_count: 50
Recall@5: 0.90
hard_filter_violations: 0
search P50: 11.75ms
search P95: 179.60ms
first-token P50: 500.27ms
first-token P95: 507.07ms
warmup_detail_failures: 0
detail_failures: 0
HTTP failures: 0
```

四项 P1 门槛全部通过：

- [x] Recall@5 不低于 0.90。
- [x] 可靠硬条件违规结果为 0。
- [x] 推荐列表预热 P95 不超过 1 秒。
- [x] 详细回答首字预热 P95 不超过 3 秒。

### 3.3 HTTP/Web UI 冒烟

```text
GET /health        -> 200
GET /ready         -> 200
GET /              -> 200
GET /static/app.js -> 200
```

测试使用的临时 CookQA API 进程已停止；Neo4j Windows 服务保持运行。

## 4. P2 工程收口

### 4.1 P2A：已完成

2026-07-15 在真实 Neo4j、Ollama 和现有 200 道菜活动索引上完成验收：

```text
default pytest: 115 passed, 2 deselected, 0 warnings
integration pytest: 2 passed, 114 deselected
Recall@5: 0.90
hard_filter_violations: 0
search P50: 14.48ms
search P95: 218.66ms
first-token P50: 548.59ms
first-token P95: 554.30ms
benchmark failures: 0
cold-start success: 5/5
cold-start ready P50: 1718.12ms
cold-start ready P95: 1777.52ms
cold-start first-search P50: 3.22ms
cold-start first-search P95: 3.72ms
Ruff: All checks passed!
pip check: No broken requirements found.
```

已完成事项：

- [x] 使用 httpx ASGI transport 替换弃用的 FastAPI TestClient 测试路径。
- [x] 增加默认隔离、显式 `-m integration` 启用的真实服务测试。
- [x] benchmark 保存未命中案例、意图汇总、降级组件和安全失败类别。
- [x] 使用独立报告重复测量新 API 进程的首次 ready 和首次搜索。

P2A 运行产物位于 Git 忽略的 `Data/runtime/benchmark-report.json` 和 `Data/runtime/cold-start-report.json`。

### 4.2 P2B：已完成

已实现：

- [x] 幂等创建并校验 Recipe 复合唯一约束、版本索引和分类节点名称唯一约束。
- [x] 关系属性只写入非空值，空 `amount` / `unit` 不再写入 Neo4j。
- [x] `config/recipe-selection-mvp.txt` 成为唯一 MVP 清单，删除无运行引用的空清单。
- [x] 清理默认 dry-run，保护活动版本、上一版本和显式保留版本。
- [x] 激活、回滚和清理写入 `Data/runtime/index-operations.jsonl`。
- [x] 新增 [`INDEX_RECOVERY.md`](INDEX_RECOVERY.md) 恢复手册。

2026-07-15 最终真实验收：

```text
default pytest: 123 passed, 2 deselected, 0 warnings
integration pytest: 2 passed, 123 deselected
new active recipe count: 200
retained previous recipe count: 200
named constraints: 6
named Recipe data-version indexes: 1
cleanup dry-run candidates: 0
cleanup invalid local entries: 0
cleanup graph-only versions: 0
validated rollback: success
final version restore: success
Recall@5: 0.90
hard_filter_violations: 0
search P50: 14.04ms
search P95: 271.83ms
first-token P50: 529.56ms
first-token P95: 543.11ms
benchmark failures: 0
cold-start success: 5/5
cold-start ready P50: 1711.49ms
cold-start ready P95: 2308.97ms
cold-start first-search P50: 2.88ms
cold-start first-search P95: 3.18ms
HTTP/Web UI smoke: 200 / 200 / 200 / 200
Ruff: All checks passed!
pip check: No broken requirements found.
```

活动指针最终指向本轮新构建版本，上一版本仍保留并已验证可回滚。benchmark、cold-start 和操作审计均位于 Git 忽略的 `Data/runtime/`，未提交密码或运行数据。

## 5. 工作区说明

Phase 2 在隔离 worktree 分支 `codex/cookqa-p2` 中实施。结构化补丁工具更新已有文件时仍会返回 `windows sandbox: helper_unknown_error: setup refresh had errors`；本轮已有文件修改均通过先校验后应用的 unified diff 完成，没有使用 PowerShell/Python 直接改写源码。

原始 checkout 中未跟踪的 `tests/.sandbox-probe` 属于既有沙箱探针，本轮未修改，也未进入隔离 worktree 或任何提交。
