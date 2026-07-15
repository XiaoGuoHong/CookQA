# CookQA 索引版本运维与恢复

本文适用于 Windows 本机 CookQA MVP。`Data/runtime/active.json` 是唯一活动版本指针；Neo4j、BM25 和 FAISS 必须使用同一个 `data_version`。所有命令都应在仓库根目录执行。

## 1. 前置检查

1. 确认 Neo4j Windows 服务与 Ollama 正在运行。
2. 确认当前 PowerShell 已设置 `NEO4J_PASSWORD`；不要把真实密码写入命令历史、脚本、文档或 Git。
3. 确认 `Data/source/howtocook` 位于 `config/howtocook-source.json` 固定的提交。
4. MVP 构建只使用 `config/recipe-selection-mvp.txt`；该清单固定 200 道菜。

## 2. 构建、验证与激活

```powershell
.\scripts\build-indexes.ps1
```

构建顺序为：幂等创建并验证 Neo4j schema、写入候选图版本、构建 BM25/FAISS、校验 manifest 与 ID 集，最后原子替换 `Data/runtime/active.json`。任何激活前失败都不会改变当前活动指针。

构建成功后检查：

```powershell
Get-Content Data/runtime/active.json
python -m cookqa.cli serve --host 127.0.0.1 --port 8000
```

另开 PowerShell 验证：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/ready
$env:COOKQA_INTEGRATION_BASE_URL='http://127.0.0.1:8000'
python -m pytest -q -m integration -p no:cacheprovider
```

`/ready` 必须返回 200，并显示 200 道菜及 Neo4j/Ollama 组件就绪。

## 3. 历史版本清理

手动清理默认只预览，不删除：

```powershell
python -m cookqa.cli cleanup-indexes --data-dir Data
```

输出中的 `protected_versions` 始终包含当前活动版本和最近一个可回滚版本。可额外保护指定版本：

```powershell
python -m cookqa.cli cleanup-indexes --data-dir Data --keep VERSION_TO_KEEP
```

只有确认 `candidate_versions`、`invalid_local_entries` 和 `graph_only_versions` 后，才显式执行：

```powershell
python -m cookqa.cli cleanup-indexes --data-dir Data --keep VERSION_TO_KEEP --apply
```

正式清理只处理 `Data/indexes/<version>/index-manifest.json` 存在且 manifest 版本与目录名一致的历史目录，并逐版本同步删除 Neo4j Recipe 数据和本地目录。无效目录及仅存在于 Neo4j 的版本只报告，不自动删除。

成功构建后的自动历史清理复用同一规划器，并始终保护新活动版本和上一版本。

## 4. 验证并回滚

```powershell
python -m cookqa.cli rollback-indexes --data-dir Data
```

回滚前会加载上一版本的 manifest、BM25、FAISS 和菜谱，校验 Neo4j ID 集、版本和向量维度。只有全部通过才交换 `active.json` 中的当前/上一版本。回滚后重新执行 `/ready`、integration 测试和必要的固定 benchmark。

## 5. 故障恢复顺序

- 构建或 schema 失败：保留当前 `active.json`，修复原因后重新构建；未激活候选会被尽力清理。
- 激活失败：当前指针不变；检查 `Data/runtime/` 写权限后重新构建。
- 清理失败：活动版本不回退。先运行 dry-run，核对已删除版本和剩余候选，再决定是否重试 `--apply`。
- 回滚校验失败：当前指针不变；检查上一版本本地 artifact 与 Neo4j 数据是否一致。
- `graph_only_versions` 非空：不要手工执行宽范围 Cypher 删除。先恢复对应本地 artifact 或通过受审计的逐版本流程处理。
- `invalid_local_entries` 非空：不要把该目录作为可恢复版本；先核对 manifest 与目录名。

## 6. 审计与安全

结构化操作日志位于 `Data/runtime/index-operations.jsonl`，记录 UTC 时间、操作、源版本、目标版本、结果、安全错误类别和清理计划。该路径已被 Git 忽略。

日志不记录密码、Token、Cookie、Authorization 请求头或完整异常文本。排查时可以分享版本号和错误类别，但不得复制环境变量值或连接凭据。
