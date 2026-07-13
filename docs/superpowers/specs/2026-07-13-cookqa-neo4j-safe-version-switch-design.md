# CookQA Neo4j 安全版本切换设计

**日期：** 2026-07-13  
**状态：** 已确认，待实施  
**适用环境：** Windows 单机、单实例

## 1. 目标

为 CookQA 的 Neo4j 图索引增加版本化构建、安全切换和可回滚能力，使 BM25、FAISS、Neo4j 始终使用同一个 `data_version`。

成功标准：

- 构建新版本时不删除或覆盖当前活动图数据。
- 新版本完成写入和校验后才允许切换。
- 写入中断、校验失败、文件发布失败或指针切换失败时，旧版本仍可查询。
- 成功切换后保留当前版本和上一版本，并可安全回滚。
- 所有 Neo4j 检索都显式限制到当前 `data_version`。

## 2. 范围与非目标

本次只处理 P0 的 Neo4j 安全版本切换，不包含结构化菜谱对比、查询类型扩展或多机部署。

明确约束：

- 部署模型保持 Windows 单机、单实例。
- `Data/runtime/active.json` 是唯一活动版本指针。
- 不在 Neo4j 中增加第二套活动状态指针。
- 不引入新依赖，不使用 Neo4j 多数据库，不实现跨机器索引分发。
- 不自动回滚；回滚必须由明确的运维动作触发。

## 3. 方案选择

采用“版本化 Recipe 节点 + 本地活动指针”方案。

未采用的方案：

- 每版本独立 Neo4j 数据库：隔离更强，但创建、切换和清理成本超出当前 MVP 需要。
- 节点 `active=true/false` 批量翻转：切换不是单点原子操作，中断时可能出现双活动或无活动状态。
- Neo4j 内部活动指针：适合多实例或外部直接查询，但会与本地 BM25/FAISS 形成双状态协调问题。

## 4. 版本模型

Recipe 节点使用 `recipe_id` 和 `data_version` 联合标识：

```cypher
MERGE (recipe:Recipe {
  recipe_id: item.recipe_id,
  data_version: $data_version
})
```

Ingredient、Category、Tool 等维度节点保持全局复用。不同版本的 Recipe 节点分别建立到这些维度节点的关系，因此删除某个 Recipe 版本不会破坏其他版本。

所有 Recipe 查询必须包含：

```cypher
recipe.data_version = $data_version
```

用户输入和值继续通过 Cypher 参数传递，不拼接到查询文本中。

## 5. 活动版本指针

`Data/runtime/active.json` 保存当前版本和上一版本：

```json
{
  "version": "new-version",
  "previous_version": "old-version"
}
```

规则：

- `version` 是运行时唯一生效版本。
- `previous_version` 用于回滚和保留策略；首次构建时允许为空或缺省。
- 指针通过同目录临时文件加 `os.replace` 原子更新。
- 运行时忽略未被指针引用的候选版本。

## 6. 组件职责

### 6.1 `cookqa/indexing/neo4j_writer.py`

Neo4j 写入器提供四项明确能力：

- `write_version(recipes, data_version)`：幂等写入指定版本，不删除其他版本。
- `validate_version(recipes, data_version)`：验证 Recipe 数量和 `recipe_id` 集合完全一致。
- `delete_version(data_version)`：只删除指定候选版本的 Recipe 节点及其关系。
- `cleanup_versions(keep_versions)`：删除保留集合之外的 Recipe 版本。

写入器不负责切换活动版本，也不读取 `active.json`。

### 6.2 `cookqa/indexing/builder.py`

构建器负责跨本地索引和 Neo4j 的顺序编排：

1. 在 staging 目录构建 BM25 和 FAISS。
2. 写入新的 Neo4j `data_version`。
3. 校验 Neo4j Recipe 数量和 ID 集合。
4. 生成并校验 manifest。
5. 将本地索引发布到 `Data/indexes/<data_version>/`。
6. 原子更新 `active.json`，并记录旧活动版本为 `previous_version`。
7. 最佳努力清理更老版本，只保留当前和上一版本。

构建器不得在第 6 步之前改变活动版本。

### 6.3 `cookqa/retrieval/neo4j_store.py`

`Neo4jRetriever` 在初始化时接收当前 `data_version`。候选查询把该值作为必需参数传入，任何调用都不能省略版本过滤。

### 6.4 `cookqa/runtime.py`

运行时从 `active.json` 读取当前版本，加载对应 manifest、BM25 和 FAISS，并使用同一个版本创建 `Neo4jRetriever`。`/ready` 只检查当前活动版本，不受未激活候选版本影响。

## 7. 构建与切换数据流

```text
输入菜谱
  -> staging 本地索引
  -> 写入候选 Neo4j 版本
  -> 校验三个索引的一致性
  -> 发布不可变本地版本目录
  -> 原子切换 active.json
  -> 最佳努力清理历史版本
```

该顺序不提供跨文件系统和 Neo4j 的分布式事务，而是把唯一可见性切换点收敛到最后一次 `active.json` 原子替换。切换前产生的候选数据不会被运行时查询。

## 8. 失败处理

| 失败阶段 | 处理方式 | 活动版本结果 |
| --- | --- | --- |
| 本地 staging 构建失败 | 删除 staging | 旧版本不变 |
| Neo4j 写入中断 | 尝试删除候选 `data_version` | 旧版本不变 |
| Neo4j 或 manifest 校验失败 | 删除候选图版本和 staging | 旧版本不变 |
| 本地版本目录发布失败 | 删除或保留不可见候选图版本供后续清理 | 旧版本不变 |
| `active.json` 原子替换失败 | 不清理旧版本；候选保持不可见 | 旧版本不变 |
| 切换后历史清理失败 | 记录警告，保留额外非活动版本 | 新版本继续生效 |

清理是切换后的非关键步骤，清理失败不能把已经可用的新版本标记为构建失败。

错误日志只记录阶段、版本标识和异常类型，不输出 Neo4j 密码、Token、连接凭据或 Authorization 信息。

## 9. 回滚

回滚只改变本地活动指针，不重写 Neo4j 数据：

1. 读取当前 `version` 和 `previous_version`。
2. 验证上一版本目录、manifest、BM25、FAISS 和 Neo4j Recipe 集合。
3. 验证通过后原子写入新的 `active.json`：原 `previous_version` 成为 `version`，原 `version` 成为 `previous_version`。
4. 验证或指针替换失败时保持原指针不变。

回滚后不立即清理刚退出的版本，使其可以再次前滚。自动故障探测和自动回滚不在本次范围内。

## 10. 测试设计

### 10.1 Neo4j 写入单元测试

- 写入查询不包含全局 `MATCH (recipe:Recipe) DETACH DELETE recipe`。
- Recipe 的 `MERGE` 同时包含 `recipe_id` 和 `data_version`。
- `delete_version` 只删除指定版本。
- `cleanup_versions` 保留传入的当前版本和上一版本。
- 验证数量不符、ID 缺失或出现额外 ID 时失败。

### 10.2 检索与运行时测试

- 所有候选查询包含 `$data_version`，并保持用户输入参数化。
- `Neo4jRetriever` 使用 manifest 对应的活动版本。
- `/ready` 只验证活动版本；不可见候选版本不影响就绪状态。

### 10.3 构建故障注入测试

- Neo4j 写入中断时旧 `active.json` 不变。
- 新图验证失败时旧版本仍可查询。
- 本地发布失败时旧指针不变。
- 模拟 `os.replace` 失败时旧指针不变。
- 清理失败时新版本仍成功生效。
- 成功切换后当前版本和上一版本都存在，更老版本可以清理。

### 10.4 回滚测试

- 上一版本校验失败时拒绝回滚。
- 指针切换失败时当前版本不变。
- 回滚成功后 BM25、FAISS 和 Neo4j 都使用同一旧版本。

## 11. 验收标准

- 人为注入写入中断、校验失败、发布失败和切换失败后，旧活动版本仍可提供查询。
- 成功构建后 `active.json.version` 指向新版本，`previous_version` 指向旧版本。
- 成功回滚后三个索引统一恢复到上一版本。
- 代码中不存在构建前全局删除 Recipe 的路径。
- 完整 pytest、Ruff 和敏感信息扫描通过。

