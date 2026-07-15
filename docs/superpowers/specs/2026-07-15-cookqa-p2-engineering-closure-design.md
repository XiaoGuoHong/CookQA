# CookQA Phase 2 工程收口设计

## 目标

在不改变 CookQA 现有检索、排序和回答语义的前提下，分两个阶段完成
`docs/UNFINISHED.md` 中列出的 Phase 2 工程收口事项。Phase 2 结束时，项目应具备：

- 无已知 TestClient/httpx 弃用警告的默认测试套件；
- 默认隔离、显式启用的真实 Neo4j/Ollama 集成测试；
- 可定位未命中案例、意图质量和组件降级的 benchmark 报告；
- 与预热性能分离、可重复执行的 API 冷启动测量；
- 可幂等创建和验证的 Neo4j 必要约束与索引；
- 可审计的索引版本切换、回滚、历史清理和恢复说明；
- 对两个菜谱选择配置文件的单一、明确职责定义。

Phase 2 仍是 Windows 本地 Graph RAG MVP 的工程收口，不将项目描述为生产平台，
也不新增云服务、鉴权系统、后台管理界面或新的检索架构。

## 交付拆分

### P2A：可重复验证能力

P2A 先建立后续数据库和运维改动所需的验证基础，范围包括：

1. 消除默认 pytest 中 FastAPI TestClient/httpx 兼容层弃用警告；
2. 增加真实 Neo4j/Ollama 集成测试标记、默认隔离规则和独立运行说明；
3. 扩展 benchmark 报告，保存未命中案例、意图统计和组件降级汇总；
4. 增加独立的 API 冷启动测量，不污染现有预热 P50/P95。

P2A 通过后才进入 P2B。P2A 不修改检索语义、排序权重、模型选择或索引格式。

### P2B：数据与运维收口

P2B 在 P2A 验证能力之上完成：

1. 为 Neo4j 增加必要约束和索引，并减少已知 schema 通知噪声；
2. 明确 `config/recipe-selection-mvp.txt` 与 `config/recipe-selection.txt` 的职责；
3. 补齐索引版本切换、回滚、历史清理的长期日志和恢复手册；
4. 在真实 200 道菜索引和 50 条固定查询上完成最终回归。

## 架构与组件边界

### 测试层

默认测试只覆盖可在仓库内独立运行的行为，不连接真实 Neo4j/Ollama。真实服务测试使用
pytest 的 `integration` 标记，并只在显式传入 `-m integration` 时运行。集成测试复用正式
配置和运行时入口，但不得打印密码、Authorization 请求头或敏感环境变量。

弃用警告优先通过更新测试调用方式或明确兼容依赖解决。只有确认警告来自不可控的第三方
兼容层且无法在当前依赖范围内消除时，才允许增加精确到警告类型和消息的过滤规则；不得
使用全局忽略掩盖其他弃用警告。

### Benchmark 层

`scripts/benchmark.py` 继续通过正式 HTTP API 执行固定 50 条查询，不绕过生产检索链路。
现有 Recall@5、硬条件违规、搜索延迟和首字延迟保持兼容。报告新增：

- 未命中案例：case ID、查询、期望 recipe IDs、实际 top-k recipe IDs；
- 意图统计：每个意图的案例数、命中数、未命中数和召回摘要；
- 降级汇总：每个组件出现降级的查询数和案例 IDs；
- 失败摘要：HTTP、详情、预热和流式回答失败的安全错误类别。

新增字段只追加到现有 JSON 结构，避免破坏已有报告消费者。报告不得保存响应请求头、
环境变量或连接凭据。

### 冷启动测量

冷启动与预热 benchmark 使用独立入口和独立报告。一次冷启动样本定义为：

1. 启动一个新的 CookQA API 进程；
2. 等待首次 `/ready` 成功；
3. 执行首次固定搜索请求；
4. 记录进程启动到 ready 的耗时及首次搜索耗时；
5. 终止本轮启动的 API 进程。

冷启动不强制卸载 Ollama 模型，也不重启 Neo4j 服务。这样测量的是 CookQA API 和本地
索引加载成本，避免把外部服务重启和模型卸载策略混入不可重复的结果。每个样本必须有明确
状态；失败不得用 `null` 代替后继续判定成功。

### Neo4j schema

schema 管理保持在索引构建路径内，由参数化、幂等的 Cypher 创建必要约束与索引。约束和
索引名称固定，重复构建不得失败。具体 schema 以现有查询访问模式为准，只为实际用于版本
隔离、菜谱定位和关系查询的字段增加条目，不提前为未使用字段建索引。

schema 验证通过 `SHOW CONSTRAINTS`、`SHOW INDEXES` 和真实 200 道菜构建结果完成。候选版本
构建或 schema 校验失败时，不更新 `Data/runtime/active.json`，也不删除当前活动版本。

### 版本日志、清理与恢复

版本切换和回滚沿用现有原子激活机制。P2B 在 Git 忽略的 `Data/runtime/` 下增加结构化运维
日志，记录时间、操作、源版本、目标版本、结果和安全错误类别。日志不包含密码和完整异常
上下文中的敏感值。

历史清理必须先支持 dry-run。默认保护：

- 当前活动版本；
- 最近一个可回滚版本；
- 用户显式指定保留的版本。

实际删除只允许作用于 `Data/indexes/` 下已验证的历史版本目录，并与 Neo4j 中相同数据版本
同步处理。恢复手册说明构建、激活、验证、回滚、dry-run 和正式清理顺序。

### 菜谱选择配置

`config/recipe-selection-mvp.txt` 是当前固定 200 道菜的唯一 MVP 构建和验收输入。
`config/recipe-selection.txt` 不得被运行路径隐式读取；若仓库中没有确认的独立用途，则在
P2B 中删除该空文件，并在 README 中只保留 MVP 清单说明。

## 数据流

P2A 的验证数据流为：固定评测集进入正式 HTTP API，API 返回查询计划、结果、耗时和降级
状态，benchmark 聚合后写入 Git 忽略的 JSON 报告。集成测试使用相同运行时入口验证活动
manifest、BM25、FAISS、Neo4j 数据版本和 Ollama 模型一致性。

P2B 的索引数据流保持现状：固定 HowToCook 源版本经过解析和规范化，构建候选 BM25、FAISS
与 Neo4j 数据版本，完成 manifest、ID 集、向量维度和 schema 校验后才原子激活。清理流程
只处理未受保护的历史版本。

## 错误处理与安全

- 默认测试发现外部服务缺失时不得静默转为通过；默认测试不进入外部服务路径。
- 显式集成测试缺少必要配置时应跳过并说明缺少的配置类别；服务已配置但不可用时应失败。
- benchmark 和 cold-start 任一必需样本失败时，报告保留安全失败摘要，验收结果为失败。
- Neo4j schema、候选构建、激活和清理任一步失败时保持当前活动版本不变。
- 所有日志、测试输出、报告和文档均不得保存或复述真实密码、Token、Cookie、请求头或私钥。

## 验收标准

### P2A 门槛

执行默认质量门：

```powershell
$env:TEMP="$PWD\.tmp\pytest-temp"
$env:TMP=$env:TEMP
New-Item -ItemType Directory -Force $env:TEMP | Out-Null
python -m pytest -q -p no:cacheprovider
python -m ruff check .
python -m pip check
git diff --check
```

必须满足：

- 默认测试全部通过；
- 无 TestClient/httpx 弃用警告；
- 默认测试不连接 Neo4j/Ollama；
- `python -m pytest -q -m integration -p no:cacheprovider` 能显式运行真实服务测试；
- benchmark 新增诊断字段的单元测试通过，旧字段保持兼容；
- cold-start 单元测试覆盖成功、超时、启动失败和首次搜索失败；
- Ruff、pip check 和 diff check 全部通过。

### P2B 门槛

必须满足：

- schema 可重复创建，约束和索引与现有查询模式一致；
- 真实 200 道菜候选版本构建、激活、验证和回滚各成功一次；
- 历史清理 dry-run 正确保留活动版本和最近可回滚版本；
- `recipe-selection-mvp.txt` 是唯一 MVP 运行输入，空清单不再可能被误用；
- 恢复手册和运行命令完整且不含凭据。

### 最终真实运行门槛

在真实 Neo4j、Ollama 和 200 道菜活动索引上执行固定 50 条查询，必须保持：

- Recall@5 不低于 0.90；
- 可靠硬条件违规数为 0；
- 预热搜索 P95 不超过 1000ms；
- 预热回答首字 P95 不超过 3000ms；
- HTTP、详情、预热和流式回答失败数均为 0；
- `/health`、`/ready`、`/`、`/static/app.js` 均返回 HTTP 200；
- cold-start 报告包含有效样本数、成功数、失败数、P50/P95 和逐样本状态。

Phase 2 完成状态只在 P2A、P2B 和最终真实运行门槛全部通过后更新。若外部服务不可用，允许
完成代码和默认测试，但必须将 Phase 2 标记为“实现完成、真实验收待执行”，不能宣称完成。

## 预计改动范围

预计只修改与 Phase 2 直接相关的文件：

- `pytest.ini`、`pyproject.toml` 和测试文件；
- `scripts/benchmark.py` 及冷启动测量脚本；
- `cookqa/indexing/` 下的 Neo4j schema、激活或清理相关模块；
- 必要的 CLI/PowerShell 入口；
- `README.md`、`docs/UNFINISHED.md` 和恢复手册；
- `config/recipe-selection.txt`（仅在确认无运行引用后删除）。

不重构无关模块，不改变 Web UI，不引入新依赖，不提交 `Data/` 运行产物，也不触碰已有未
跟踪的 `tests/.sandbox-probe`。
