# CookQA 未完成事项

- 更新日期：2026-07-13
- 当前状态：主要代码骨架已落地，但尚未满足设计文档的完整验收标准
- 目标平台：Windows 本机
- 设计基线：[`docs/superpowers/specs/2026-07-13-cookqa-graph-rag-design.md`](superpowers/specs/2026-07-13-cookqa-graph-rag-design.md)
- 实施计划：[`docs/superpowers/plans/2026-07-13-cookqa-graph-rag-implementation.md`](superpowers/plans/2026-07-13-cookqa-graph-rag-implementation.md)

## 1. 当前结论

CookQA 已经具备领域模型、HowToCook 解析、确定性查询路由、混合检索协调、FastAPI 接口、Ollama 适配器、静态 Web UI、索引构建框架、固定数据选择和评测集。

当前版本只能视为“实现中的本地 Graph RAG MVP”，不能宣称完整完成或性能达标。真实 FAISS 已完成；Neo4j 安全切换、菜谱比较、完整本地集成、评测和性能验收仍未闭环。

## 2. 已落地内容

### 2.1 数据与领域层

- Pydantic 菜谱、食材、查询计划、搜索结果和就绪状态模型。
- 根据源文件相对路径生成稳定 `recipe_id`。
- HowToCook Markdown 确定性解析和食材别名规范化。
- 固定上游提交：`cbc524e28a88bf5ccc6e094004cfbeba1ea6fdf9`。
- 固定 200 道菜选择清单，排除了饮料、调酒、单独酱料、甜点、半成品和模板。

### 2.2 查询与检索层

- 六类查询意图的规则路由。
- BM25 稀疏召回。
- 菜谱级精确余弦稠密召回框架。
- RRF 排名融合。
- 食材、耗时、分类、工具和难度硬过滤框架。
- 检索组件失败时的显式降级信息。
- 参数化 Neo4j 查询模板，不使用 LLM 生成 Cypher。

### 2.3 应用层

- `POST /api/v1/search`。
- `GET /api/v1/recipes/{recipe_id}`。
- `POST /api/v1/recipes/{recipe_id}/answer/stream`。
- `GET /health` 和 `GET /ready`。
- 搜索、结构化详情和 LLM 生成相互分离。
- 静态 HTML、CSS、JavaScript Web UI。
- Windows 启动、索引构建和基准测试脚本。

## 3. 当前验证证据

### 3.1 自动化测试

运行命令：

```powershell
$env:TEMP="$PWD\.tmp\pytest-temp"
$env:TMP=$env:TEMP
python -m pytest -q --basetemp .tmp\pytest-unfinished-doc -o cache_dir=.tmp\pytest-cache
```

最近结果：

```text
55 passed, 1 warning in 0.59s
```

唯一警告来自当前环境的 FastAPI TestClient 兼容层：

```text
StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated
```

### 3.2 数据验证

当前选择清单已验证：

```text
SELECTION_COUNT 200
PARSED_COUNT 200
UNIQUE_IDS 200
```

这只能证明当前解析器能够解析选中的 200 个文件，不代表 Neo4j、稠密索引和 BM25 已在真实环境完成联合构建。

### 3.3 HTTP 冒烟

在没有活动索引的本机状态下：

```text
GET  /health                  -> 200
GET  /ready                   -> 503
GET  /                        -> 200
GET  /static/app.js           -> 200
POST /api/v1/search           -> 503
```

这证明进程存活、Web UI 可访问，并且服务不会在运行数据缺失时冒充就绪。

### 3.4 安全检查

- 已执行常见 API Key、Token、Bearer Token 和硬编码 Neo4j 密码模式扫描，无命中。
- `.env.example` 只包含占位符。
- 当前日志与公开错误不输出密码、Token、Cookie、Authorization 请求头或堆栈。

## 4. P0：完成前必须修复

### 4.1 使用真实 FAISS 索引（已完成）

`cookqa/retrieval/faiss_store.py` 现由 `FaissVectorIndex` 封装真实 `faiss.IndexFlatIP`，不再保留 NumPy 稠密索引兼容路径。

已完成并验证：

- 构建与查询向量使用一致的 L2 归一化。
- FAISS 二进制索引持久化为 `faiss.index`，`recipe_id` 映射单独保存为 `faiss.ids.json`。
- 加载时校验索引类型、维度、向量数量、ID 数量和重复 ID。
- FAISS 缺失、损坏或映射无效时明确标记运行数据未就绪，不静默退回 NumPy。
- 构建器和运行时均使用双文件 FAISS 工件，`/ready` 的索引状态来自真实加载与一致性校验。
- 直接 FAISS 测试 7 项、FAISS/构建/清单/运行时聚焦测试 12 项、全量测试 55 项均通过。
- `cookqa/` 与 `tests/` 中已无 `ExactVectorIndex` 或 `faiss.npz` 引用。

本项仅表示真实 FAISS 代码路径闭环；200 道菜的本地三路联合构建仍属于 P1 验收。

### 4.2 改造 Neo4j 构建和回滚

当前 `cookqa/indexing/neo4j_writer.py` 在导入前执行：

```cypher
MATCH (recipe:Recipe) DETACH DELETE recipe
```

如果后续导入或一致性校验失败，旧版本已经被删除，不满足设计文档要求的“构建失败继续使用上一版”。

必须完成：

- 新版本使用独立 `data_version` 写入，不先删除活动版本。
- 新版本节点、关系和索引全部写入后再执行一致性校验。
- 通过单一活动版本指针或等价机制完成切换。
- 切换成功后再清理过期版本，并至少保留上一版备份。
- 任何异常都不能破坏当前活动版本。
- 增加导入中断、校验失败、切换失败和回滚测试。

完成判定：人为制造新版本构建失败后，旧版本仍可查询，`/ready` 仍反映旧活动版本的真实状态。

### 4.3 补齐菜谱比较

当前查询路由能够识别 `recipe_comparison`，但检索协调器没有专用比较流程。普通 Neo4j 候选查询不能表达两道指定菜的差异。

必须完成：

- 只比较路由器识别出的两道菜，不返回无关 Top 5。
- 返回共同和不同的食材、分类、方法、工具、难度和明确耗时。
- 缺失字段显示“无法确认”，不推断为相同或不同。
- 比较结果来自结构化数据，不依赖 LLM。
- 增加服务层和 API 集成测试。

完成判定：固定评测集中的比较查询返回两道指定菜及可验证的结构化差异。

## 5. P1：真实集成与正确性收口

### 5.1 运行时加载食材别名

构建阶段会读取 `config/ingredient_aliases.json`，但运行时创建 `QueryRouter` 时还没有加载同一份别名表。必须保证“西红柿”和“番茄”等查询使用与构建阶段完全一致的规范化规则。

### 5.2 修正主观词和硬条件语义

“不辣”当前可能被简化为排除名为“辣”的食材，无法可靠覆盖辣椒、辣椒粉、豆瓣酱或规则推断标签。

必须明确：

- 明确食材排除使用规范化食材实体。
- “辣”“清淡”“下饭”等主观表达默认只参与软排序。
- 只有存在可靠结构化标签和证据时，才能将其用于硬过滤。
- 字段缺失时必须标记无法验证。

### 5.3 验证本地 HowToCook checkout

本次浅克隆命令发生超时。当前目录能读取固定提交和 200 个目标文件，但 Git 工作区状态异常，正式构建前应重新获取一个干净的固定提交 checkout，并重新验证：

```powershell
git -C Data/source/howtocook rev-parse HEAD
git -C Data/source/howtocook status --short
```

期望提交必须是：

```text
cbc524e28a88bf5ccc6e094004cfbeba1ea6fdf9
```

正式验收时不应使用状态异常的上游 checkout。

### 5.4 运行完整本地构建

必须在本机真实运行：

- Neo4j Windows ZIP 发行版。
- Ollama `qwen3.5:4b`。
- Ollama `bge-m3`。
- 200 道菜的 BM25、FAISS 和 Neo4j 联合构建。
- 跨索引数量、ID 哈希、版本和向量维度校验。

完成后 `/ready` 必须返回 200，并显示三套索引和两个 Ollama 模型均可用。

### 5.5 固定评测集验收

`evaluation/queries.jsonl` 已包含 50 条查询，但尚未在真实三路检索结果上跑出验收报告。

必须验证：

- 六类查询都有实际返回。
- 菜名和别名查询 Top 1 准确率为 100%。
- 固定评测集 Recall@5 不低于 90%。
- 可靠硬条件违规结果为 0。
- 无法验证的条件明确标记。

### 5.6 性能验收

尚未在当前机器的预热状态下获得有效性能报告。

必须分别测量：

- 冷启动耗时。
- 推荐列表 P50、P95。
- 详细回答首字 P50、P95。
- 路由、BM25、Neo4j、Embedding、FAISS、过滤、RRF 和序列化分阶段耗时。

目标仍为：

- 预热推荐列表 P95 不超过 1 秒。
- 预热详细回答首字 P95 不超过 3 秒。

未获得真实报告前不得声明达标。

## 6. P2：工程收口

- Ruff `0.15.21` 已安装并完成全仓检查，结果为 `All checks passed!`。
- 处理 FastAPI TestClient 的兼容层弃用警告。
- 增加真实 Neo4j 和 Ollama 集成测试的可选标记与运行说明。
- 检查 `config/recipe-selection.txt` 与正式 `config/recipe-selection-mvp.txt` 的职责，删除或明确废弃空清单，避免误用。
- 检查构建报告是否只记录安全的异常类型和文件路径，不记录凭据或请求头。
- 为索引版本切换、回滚和清理增加运维日志及恢复步骤。

## 7. 当前工作区说明

### 7.1 Git 已恢复

当前目录已恢复为有效 Git 仓库，`main` 跟踪 `origin/main`，远端为 `XiaoGuoHong/CookQA`。代码、文档和删除项均可通过 Git 差异审计和提交。

### 7.2 结构化补丁工具仍不稳定

结构化补丁工具更新已有文件时仍会间歇返回 `windows sandbox: helper_unknown_error: setup refresh had errors`。本轮未使用 PowerShell/Python 直接重写源码；受影响的内容通过 Git 对象或可审计补丁写入，并在提交前执行 `git diff --check`。

本地仍有未跟踪的 `tests/.sandbox-probe`，它未被修改或提交。

## 8. 推荐继续顺序

1. 将 Neo4j 构建改为版本化写入、验证后切换和失败回滚。
2. 实现结构化菜谱比较。
3. 补齐运行时别名与硬条件语义。
4. 重新获取干净的 HowToCook 固定提交。
5. 启动本地 Neo4j 与 Ollama，完成 200 道真实构建。
6. 运行 50 条固定评测和性能基准。
7. 完成敏感信息扫描和 HTTP/Web UI 冒烟，并处理 FastAPI TestClient 兼容层警告。

每一步只修改直接相关文件，不顺手重构无关模块。

## 9. 最终完成判定

只有同时满足以下条件，才可以将 CookQA MVP 标记为完成：

- [x] 使用真实 FAISS 菜谱级索引。
- [ ] Neo4j 新版本构建失败不会破坏旧活动版本。
- [ ] 六类查询均有服务层和 API 层可验证行为。
- [ ] 200 道菜完成 BM25、FAISS、Neo4j 联合构建。
- [ ] `/ready` 在完整本地环境返回 200。
- [ ] 菜名及别名查询 Top 1 准确率为 100%。
- [ ] 固定评测集 Recall@5 不低于 90%。
- [ ] 可靠硬条件违规结果为 0。
- [ ] 推荐列表预热 P95 不超过 1 秒。
- [ ] 详细回答首字预热 P95 不超过 3 秒。
- [x] 全量自动化测试通过。
- [x] Ruff 静态检查通过。
- [x] 敏感信息扫描无命中。
- [ ] Git 工作区状态可审计，所有改动均可查看和提交。

