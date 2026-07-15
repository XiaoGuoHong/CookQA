# CookQA

CookQA 是一个 Windows 本机运行的中文菜谱 Graph RAG MVP。它从固定版本的 [HowToCook](https://github.com/Anduin2017/HowToCook) 中选择 200 道菜，以同一份规范化数据构建 BM25、菜谱级 FAISS 稠密向量索引和 Neo4j 图，并通过 FastAPI 与静态 Web UI 提供查询。

当前实现遵循 `docs/superpowers/specs/2026-07-13-cookqa-graph-rag-design.md`：检索路由完全确定化，搜索列表不等待 LLM，菜谱详情不调用 LLM，只有用户明确请求说明时才调用本机 Ollama。

## 当前状态

P1 已于 2026-07-14 在本机真实 Neo4j Windows 服务、Ollama 和 200 道菜索引上完成验收：

- 固定 50 条查询 Recall@5：`0.90`
- 可靠硬条件违规数：`0`
- 搜索 P50 / P95：`11.75ms / 179.60ms`
- 详细回答首字 P50 / P95：`500.27ms / 507.07ms`
- `/health`、`/ready`、`/`、`/static/app.js`：均为 HTTP `200`
- 自动化测试：`106 passed`；Ruff 与 `pip check` 通过

完整运行报告位于 `Data/runtime/benchmark-report.json`。`Data/` 是本地运行数据并已被 Git 忽略，因此该报告不会提交到仓库。P2 工程事项见 [`docs/UNFINISHED.md`](docs/UNFINISHED.md)。

P2A 已于 2026-07-15 完成可重复验证能力收口，本轮实测：

- 默认测试：`115 passed, 2 deselected`，无 TestClient/httpx 弃用警告
- 真实 Neo4j/Ollama integration：`2 passed, 114 deselected`
- 固定 50 条查询：Recall@5 `0.90`，硬条件违规 `0`
- 搜索 P50 / P95：`14.48ms / 218.66ms`
- 回答首字 P50 / P95：`548.59ms / 554.30ms`
- API cold-start：`5/5` 成功，ready P50 / P95 `1718.12ms / 1777.52ms`，首次搜索 P50 / P95 `3.22ms / 3.72ms`
- Ruff 与 `pip check` 通过

P2B 的 Neo4j schema、配置职责和版本运维代码已实现，正在执行真实 200 道菜重建、回滚与最终回归；验收完成前不将 Phase 2 描述为全部完成。

## 组件

- Python 3.11+
- FastAPI + 静态 HTML/CSS/JavaScript
- Neo4j Community 5.x Windows ZIP 发行版
- 本机 Ollama：`qwen3.5:4b`、`bge-m3:latest`
- BM25 + FAISS `IndexFlatIP` + Neo4j + 意图感知融合

系统不使用云端模型或云端数据库，默认只绑定 `127.0.0.1`。

## 1. 创建环境

```powershell
cd D:\WorkSpace\Code\Project100\CookQA
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev,faiss]"
```

项目已显式限制 setuptools 只发现 `api*` 与 `cookqa*`，避免把 `Data/`、`web/`、`config/` 等目录误识别为 Python 包。

如果 Windows 上暂时没有适配当前 Python 版本的 `faiss-cpu` wheel，请改用具有可用 wheel 的 Python 3.11 环境；缺少 FAISS 时不能将服务称为完整就绪。

## 2. 准备本地服务

安装 Ollama 后拉取模型：

```powershell
ollama pull qwen3.5:4b
ollama pull bge-m3:latest
```

下载 Neo4j Community 5.x Windows ZIP 并解压。若需要长期运行，可在管理员 PowerShell 中安装 Windows 服务：

```powershell
$Neo4jHome = 'D:\Neo4j\neo4j-community-5.26.28'
& "$Neo4jHome\bin\neo4j.ps1" windows-service install
Get-Service neo4j
```

首次启动前设置密码；不要把真实密码写进源码、脚本、文档或 Git：

```powershell
$Credential = Get-Credential -UserName 'neo4j' -Message '输入 Neo4j 正式密码'
$Password = $Credential.GetNetworkCredential().Password
& "$Neo4jHome\bin\neo4j-admin.ps1" dbms set-initial-password --require-password-change=false $Password
Remove-Variable Password, Credential
Start-Service neo4j
```

如果实例已经首次启动，请使用 `cypher-shell --change-password` 修改密码。应用只从环境变量读取连接信息：

```powershell
$env:NEO4J_URI='bolt://127.0.0.1:7687'
$env:NEO4J_USER='neo4j'
$env:NEO4J_PASSWORD='YOUR_PASSWORD_HERE'
```

仓库提供的 `.env.example` 只有占位符；应用不会自动读取或打印密码。

## 3. 准备固定数据源

```powershell
git clone https://github.com/Anduin2017/HowToCook.git Data/source/howtocook
git -C Data/source/howtocook checkout cbc524e28a88bf5ccc6e094004cfbeba1ea6fdf9
git -C Data/source/howtocook status --short
```

`status --short` 应为空。`config/recipe-selection-mvp.txt` 是唯一 MVP 构建清单，共 200 条；`config/howtocook-source.json` 固定了上游提交。

## 4. 构建索引

先启动 Neo4j 和 Ollama，并在当前 PowerShell 设置 `NEO4J_PASSWORD`，然后运行：

```powershell
.\scripts\build-indexes.ps1
```

构建流程会：

1. 验证 200 条源路径全部存在。
2. 确定性解析为 `recipes.jsonl`。
3. 构建 BM25 与 FAISS 稠密索引。
4. 幂等创建并验证命名 Neo4j 约束和索引。
5. 用参数化 Cypher 写入候选 Neo4j 数据版本。
6. 校验三套索引的菜谱数、ID 哈希、版本与向量维度。
7. 仅在全部通过后原子更新 `Data/runtime/active.json`。
8. 通过受保护的清理计划保留当前和上一版本，并处理更旧的已验证版本。

运行数据只写入已被 Git 忽略的 `Data/`。

### 索引版本运维

手动历史清理默认只预览：

```powershell
python -m cookqa.cli cleanup-indexes --data-dir Data
```

核对候选后才显式执行；可重复传入 `--keep VERSION` 额外保护版本：

```powershell
python -m cookqa.cli cleanup-indexes --data-dir Data --keep VERSION_TO_KEEP --apply
python -m cookqa.cli rollback-indexes --data-dir Data
```

结构化审计日志位于 Git 忽略的 `Data/runtime/index-operations.jsonl`。完整恢复顺序见 [`docs/INDEX_RECOVERY.md`](docs/INDEX_RECOVERY.md)。

## 5. 启动和使用

```powershell
.\scripts\start.ps1
```

打开 `http://127.0.0.1:8000/`。主要接口：

- `POST /api/v1/search`
- `GET /api/v1/recipes/{recipe_id}`
- `POST /api/v1/recipes/{recipe_id}/answer/stream`
- `GET /health`
- `GET /ready`

`/health` 只表示 FastAPI 进程存活。只有活动索引、Neo4j 数据和 Ollama 模型均可用时，`/ready` 才返回 200。readiness 会将未带标签的 `bge-m3` 与本机标签 `bge-m3:latest` 视为同一模型。

FAISS 在线 embedding 默认超时为 6 秒，用于容纳本地 `bge-m3` 首次冷加载；预热后的检索仍按实际耗时计量。本机端口 8000 被占用时可改用 8001：

```powershell
.\scripts\start.ps1 -Port 8001
```

## 6. 测试

该机器的系统临时目录可能拒绝 pytest 访问，使用仓库内临时目录：

```powershell
$env:TEMP="$PWD\.tmp\pytest-temp"
$env:TMP=$env:TEMP
New-Item -ItemType Directory -Force $env:TEMP | Out-Null
python -m pytest -q -p no:cacheprovider
python -m ruff check .
python -m pip check
```

默认测试排除需要真实服务的 `integration` 标记。启动完整 CookQA 服务后显式运行：

```powershell
$env:COOKQA_INTEGRATION_BASE_URL='http://127.0.0.1:8000'
python -m pytest -q -m integration -p no:cacheprovider
```

该通道验证 `/ready` 的 200 道菜 manifest、Neo4j/Ollama 组件状态和无降级搜索。服务不可用时测试会失败，不会静默跳过。测试和报告不输出 Neo4j 密码或请求凭据。

## 7. 固定评测和性能

`evaluation/queries.jsonl` 包含 50 条固定查询，覆盖精确菜谱、食材反查、条件推荐、语义推荐、相似菜谱和菜谱比较。

启动完整服务后运行：

```powershell
python scripts/benchmark.py `
  --base-url http://127.0.0.1:8000 `
  --warmups 3 `
  --timeout 30 `
  --output Data/runtime/benchmark-report.json
```

报告包含 Recall@5、硬条件违规数、搜索 P50/P95、首字 P50/P95、样本数、未命中案例、按意图汇总、降级组件和安全失败类别。2026-07-15 的真实报告中四项门槛全部为 `true`。

冷启动与暖态 benchmark 分开测量。保持 Neo4j 和 Ollama 运行，停止手动启动的 CookQA API 后执行：

```powershell
python scripts/cold_start.py `
  --samples 5 `
  --timeout 30 `
  --output Data/runtime/cold-start-report.json
```

每个样本启动一个新的 CookQA API 进程，记录首次 `/ready` 和首次固定搜索耗时，然后终止该进程。该测量不重启 Neo4j，也不卸载 Ollama 模型；任一样本失败时仍写报告并返回非零退出码。

## 安全边界

- 不记录或提交 Neo4j 密码、Token、Cookie、Authorization 请求头。
- LLM 不生成 Cypher、不参与查询路由、不决定硬过滤结果。
- 相似菜谱使用参考菜谱的已索引向量，参考无关的图候选不能覆盖 FAISS 相似度顺序。
- 强制条件字段缺失时不冒充满足。
- Neo4j 在存在硬条件时不可用，结果会明确标为“未验证”。
- 所有检索组件不可用时直接返回服务错误，不让模型凭空回答。
