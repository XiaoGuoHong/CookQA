# CookQA

CookQA 是一个 Windows 本机运行的中文菜谱 Graph RAG MVP。它从固定版本的 [HowToCook](https://github.com/Anduin2017/HowToCook) 中选择 200 道菜，以同一份规范化数据构建 BM25、菜谱级稠密向量索引和 Neo4j 图，并通过 FastAPI 与静态 Web UI 提供查询。

当前实现遵循 `docs/superpowers/specs/2026-07-13-cookqa-graph-rag-design.md`：检索路由完全确定化，搜索列表不等待 LLM，菜谱详情不调用 LLM，只有用户明确请求说明时才调用本机 Ollama。

## 组件

- Python 3.11+
- FastAPI + 静态 HTML/CSS/JavaScript
- Neo4j 5.x Windows ZIP 发行版
- 本机 Ollama：`qwen3.5:4b`、`bge-m3`
- BM25 + 精确余弦稠密索引 + RRF

系统不使用 Docker、云端模型或云端数据库，默认只绑定 `127.0.0.1`。

## 1. 创建环境

```powershell
cd D:\WorkSpace\Code\Project100\CookQA
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev,faiss]"
```

如果 Windows 上暂时没有适配当前 Python 版本的 `faiss-cpu` wheel，核心测试仍可运行，但生产构建前应换用具有可用 wheel 的 Python 3.11 环境；不要把缺少 FAISS 的状态称为完整就绪。

## 2. 准备本地服务

安装 Ollama 后拉取模型：

```powershell
ollama pull qwen3.5:4b
ollama pull bge-m3
```

下载 Neo4j 5.x Windows ZIP，解压并首次设置本地密码。只在当前终端设置敏感信息，不要写进仓库：

```powershell
$env:NEO4J_URI="bolt://127.0.0.1:7687"
$env:NEO4J_USER="neo4j"
$env:NEO4J_PASSWORD="YOUR_PASSWORD_HERE"
```

仓库提供的 `.env.example` 只有占位符；应用不会自动读取或打印密码。

## 3. 准备固定数据源

```powershell
git clone https://github.com/Anduin2017/HowToCook.git Data/source/howtocook
git -C Data/source/howtocook checkout cbc524e28a88bf5ccc6e094004cfbeba1ea6fdf9
```

固定选择位于 `config/recipe-selection-mvp.txt`，共 200 条，覆盖水产、早餐、荤菜、汤粥、主食和素菜；饮料、调酒、单独酱料、甜点、半成品和模板被排除。`config/howtocook-source.json` 固定了上游提交。

## 4. 构建索引

先启动 Neo4j 和 Ollama，然后运行：

```powershell
.\scripts\build-indexes.ps1
```

构建流程会：

1. 验证 200 条源路径全部存在。
2. 确定性解析为 `recipes.jsonl`，任何选中菜谱解析失败都会终止构建。
3. 构建 BM25 与菜谱级稠密索引。
4. 用参数化 Cypher 写入 Neo4j。
5. 校验三套索引的菜谱数、ID 哈希、版本与向量维度。
6. 仅在全部通过后原子更新 `Data/runtime/active.json`。

运行数据只写入 `Data/`，该目录已被 Git 忽略。

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

`/health` 只表示 FastAPI 进程存活。只有索引版本一致、Neo4j 数据一致且 Ollama 两个模型均可用时，`/ready` 才返回 200；否则返回 503 和不含敏感信息的组件状态。

若本机端口 8000 被占用或被 Windows 限制，可显式改用 8001：

```powershell
.\scripts\start.ps1 -Port 8001
```

## 6. 测试

该机器的系统临时目录可能拒绝 pytest 访问，使用仓库内临时目录：

```powershell
$env:TEMP="$PWD\.tmp\pytest-temp"
$env:TMP=$env:TEMP
New-Item -ItemType Directory -Force $env:TEMP | Out-Null
python -m pytest -q --basetemp .tmp\pytest-run -o cache_dir=.tmp\pytest-cache
python -m ruff check .
```

## 7. 固定评测和性能

`evaluation/queries.jsonl` 包含 50 条固定查询，覆盖精确菜谱、食材反查、条件推荐、语义推荐、相似菜谱和菜谱比较。

服务预热后运行：

```powershell
python scripts/benchmark.py --base-url http://127.0.0.1:8000
```

报告写入 `Data/runtime/benchmark-report.json`，包含 Recall@5、硬条件违规数、搜索 P95 和首字 P95。代码存在不代表指标达标；只有本机真实 Neo4j、Ollama 和 200 道索引上的报告可以作为验收证据，冷启动需要单独测量。

## 安全边界

- 不记录 Neo4j 密码、Token、Cookie 或 Authorization 请求头。
- LLM 不生成 Cypher、不参与查询路由、不决定检索权重。
- 强制条件字段缺失时不冒充满足。
- Neo4j 在存在硬条件时不可用，结果会明确标为“未验证”。
- 所有检索组件不可用时直接返回服务错误，不让模型凭空回答。
