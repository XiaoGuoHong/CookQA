# CookQA 食神

CookQA 是一个中文食谱问答系统。它会读取
[Anduin2017/HowToCook](https://github.com/Anduin2017/HowToCook) 的菜谱数据，
用 FAISS 做向量检索，用 Ollama 的 `bge-m3` 做文本向量，用聊天模型生成回答。

你可以问它：

- `牛肉可以怎么做`
- `番茄炒蛋怎么做`
- `黯然销魂饭怎么做`

系统会返回相关菜谱、匹配原因、食材、简要步骤和来源。

## 这个项目能做什么

- 解析 HowToCook 里的 Markdown 菜谱。
- 生成菜谱元数据和轻量图关系，例如菜名、别名、分类、食材关系。
- 生成两套 FAISS 索引：菜谱级索引和步骤级索引。
- 提供 FastAPI 接口，支持搜索菜谱和聊天式问答。
- 支持本地运行，也支持 Docker 部署。

## 目录说明

```text
CookQA/
├─ api/                  FastAPI 应用入口
├─ cookqa/               核心代码：解析、图关系、索引、检索、生成
├─ data/                 本地数据目录，默认不提交 Git
│  ├─ HowToCook/         你放入或克隆的 HowToCook 数据
│  ├─ parsed/            解析后的菜谱 JSON
│  ├─ graph/             图关系 JSON
│  └─ indexes/           FAISS 索引和 payload
├─ tests/                自动化测试
├─ main.py               命令行入口
├─ Dockerfile            Docker 镜像构建文件
└─ docker-compose.yml    Docker Compose 启动文件
```

## 准备工作

你需要先准备这些东西：

1. Python 3.11，推荐用 Conda 环境。
2. Ollama，并确认 Ollama 能正常启动。
3. Ollama 里有这两个模型：

```powershell
ollama pull bge-m3
ollama pull gpt-oss:120b-cloud
```

`bge-m3` 用来建向量索引，必须有。`gpt-oss:120b-cloud` 用来生成最终回答；
如果你本地用的是别的聊天模型，可以通过 `OLLAMA_CHAT_MODEL` 改掉。

4. HowToCook 菜谱数据。推荐放在：

```text
CookQA/data/HowToCook
```

可以这样下载：

```powershell
git clone https://github.com/Anduin2017/HowToCook.git data/HowToCook
```

如果你不会用 Git，也可以从 GitHub 下载 zip，解压后把里面的内容放到
`data/HowToCook`，确保最后存在这个目录：

```text
data/HowToCook/dishes
```

## 本地运行

下面以 Windows PowerShell + Conda 为例。

### 1. 进入项目目录

```powershell
cd D:\WorkSpace\Code\Project100\CookQA
```

### 2. 创建并进入 Conda 环境

```powershell
conda create -n cookqa python=3.11 -y
conda activate cookqa
```

如果你已经有自己的 Python 3.11 环境，可以跳过这一步。

### 3. 安装依赖

```powershell
pip install -r requirements.txt
```

### 4. 配置环境变量

PowerShell 当前窗口里执行：

```powershell
$env:HOWTOCOOK_PATH="D:\WorkSpace\Code\Project100\CookQA\data\HowToCook"
$env:COOKQA_DATA_DIR="D:\WorkSpace\Code\Project100\CookQA\data"
$env:OLLAMA_BASE_URL="http://127.0.0.1:11434"
$env:OLLAMA_EMBEDDING_MODEL="bge-m3"
$env:OLLAMA_CHAT_MODEL="gpt-oss:120b-cloud"
$env:OLLAMA_TIMEOUT="600"
$env:OLLAMA_EMBED_BATCH_SIZE="1"
```

如果你的项目路径不一样，把上面的路径改成你自己的。

### 5. 确认 Ollama 正常

先启动 Ollama。一般打开 Ollama 桌面程序即可，也可以在终端运行：

```powershell
ollama serve
```

再开一个新的 PowerShell，检查模型：

```powershell
ollama list
```

你应该能看到 `bge-m3`。如果要使用聊天回答，也应该能看到你的聊天模型。

### 6. 建索引

第一次使用必须先建索引。

只解析菜谱和图关系，不生成向量：

```powershell
python main.py rebuild --metadata-only
```

完整建索引，包含 FAISS 向量索引：

```powershell
python main.py rebuild
```

完整建索引会调用 Ollama 的 `bge-m3`，第一次可能需要几分钟到十几分钟。
完成后会生成这些文件：

```text
data/parsed/recipes.json
data/graph/relations.json
data/indexes/recipes.faiss
data/indexes/recipes.payload.json
data/indexes/steps.faiss
data/indexes/steps.payload.json
```

### 7. 启动 API 服务

```powershell
uvicorn api.app:app --host 127.0.0.1 --port 8000
```

看到类似下面的输出就说明启动成功：

```text
Uvicorn running on http://127.0.0.1:8000
```

浏览器打开：

```text
http://127.0.0.1:8000/docs
```

这里是 FastAPI 自动生成的接口页面，新手推荐先从这个页面测试。

## 怎么提问

### 方法一：在浏览器里测试

打开：

```text
http://127.0.0.1:8000/docs
```

找到 `POST /api/v1/chat`，点 `Try it out`，填入：

```json
{
  "question": "番茄炒蛋怎么做",
  "top_k": 5,
  "include_steps": true
}
```

然后点 `Execute`。

### 方法二：PowerShell 调用聊天接口

```powershell
$body = @{
  question = "番茄炒蛋怎么做"
  top_k = 5
  include_steps = $true
} | ConvertTo-Json

Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/api/v1/chat" `
  -Method Post `
  -ContentType "application/json; charset=utf-8" `
  -Body $body
```

### 方法三：只搜索，不调用聊天模型

如果你只想看推荐菜谱，不想调用聊天模型，可以用搜索接口：

```powershell
Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/api/v1/recipes/search?q=牛肉可以怎么做&top_k=5" `
  -Method Get
```

## 常用接口

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| `GET` | `/health` | 检查服务是否启动 |
| `POST` | `/api/v1/chat` | 聊天式问答，会返回回答和推荐菜谱 |
| `GET` | `/api/v1/recipes/search?q=...&top_k=5` | 只检索推荐菜谱 |
| `GET` | `/api/v1/recipes/{recipe_id}` | 查看某个菜谱详情 |
| `POST` | `/api/v1/index/rebuild?vectors=false` | 重新解析元数据 |
| `POST` | `/api/v1/index/rebuild?vectors=true` | 重新解析并重建向量索引 |

生产环境建议把 `COOKQA_ENABLE_REBUILD_API` 设成 `false`，避免别人通过接口触发重建索引。

## Docker 部署

Docker 只运行 CookQA 服务。Ollama 仍然运行在宿主机上。

### 1. 确认宿主机 Ollama 正常

在宿主机执行：

```powershell
ollama list
```

确认有 `bge-m3` 和聊天模型。

### 2. 准备数据

确保项目里有：

```text
data/HowToCook/dishes
```

### 3. 启动 Docker 服务

```powershell
docker compose up --build
```

启动后访问：

```text
http://127.0.0.1:8000/docs
```

### 4. 在 Docker 里建索引

另开一个 PowerShell：

```powershell
docker compose exec cookqa python main.py rebuild
```

也可以通过接口触发：

```powershell
Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/api/v1/index/rebuild?vectors=true" `
  -Method Post
```

Docker Compose 默认用这个地址访问宿主机 Ollama：

```text
http://host.docker.internal:11434
```

如果你不是 Windows/macOS Docker Desktop，可能需要按你的 Docker 网络环境修改
`OLLAMA_BASE_URL`。

## 环境变量说明

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `COOKQA_DATA_DIR` | `项目目录/data` | CookQA 数据输出目录 |
| `HOWTOCOOK_PATH` | `COOKQA_DATA_DIR/HowToCook` | HowToCook 数据目录 |
| `OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | Ollama 服务地址 |
| `OLLAMA_EMBEDDING_MODEL` | `bge-m3` | 向量模型 |
| `OLLAMA_CHAT_MODEL` | `gpt-oss:120b-cloud` | 聊天模型 |
| `OLLAMA_TIMEOUT` | `600` | Ollama 请求超时时间，单位秒 |
| `OLLAMA_EMBED_BATCH_SIZE` | `1` | 建索引时每批发给 Ollama 的文本数量 |
| `COOKQA_TOP_K` | `5` | 默认返回推荐数量 |
| `COOKQA_MIN_SCORE` | `0.15` | 预留的最低分阈值 |
| `COOKQA_ENABLE_REBUILD_API` | `true` | 是否允许通过 API 重建索引 |

如果建索引卡住或超时，优先把 `OLLAMA_EMBED_BATCH_SIZE` 保持为 `1`。

## 命令行问答

除了 API，也可以直接用命令行问：

```powershell
python main.py chat "牛肉可以怎么做"
```

命令行问答会调用聊天模型。如果你只想验证索引，建议优先用
`/api/v1/recipes/search` 搜索接口。

## 常见问题

### 1. 报错：连接不上 Ollama

先检查 Ollama 是否启动：

```powershell
ollama list
```

再检查地址是否正确：

```powershell
$env:OLLAMA_BASE_URL="http://127.0.0.1:11434"
```

Docker 里通常要用：

```text
http://host.docker.internal:11434
```

### 2. 搜不到菜谱，或者结果为空

通常是还没建索引。先执行：

```powershell
python main.py rebuild
```

再重启 API。

### 3. 提示找不到 HowToCook

检查这个目录是否存在：

```text
data/HowToCook/dishes
```

如果没有，重新下载 HowToCook：

```powershell
git clone https://github.com/Anduin2017/HowToCook.git data/HowToCook
```

### 4. PowerShell 里中文显示乱码

接口本身支持中文。PowerShell 有时会显示编码问题。建议优先用浏览器打开
`http://127.0.0.1:8000/docs` 测试，或者使用本文里的 `Invoke-RestMethod` 示例。

### 5. 第一次建索引很慢

这是正常的。系统需要把几百个菜谱和几千个步骤都发给 `bge-m3` 生成向量。
完成后索引会保存在 `data/indexes`，以后启动服务会直接加载现有索引。

## 开发和测试

运行测试：

```powershell
python -m pytest tests -q
```

只重建元数据：

```powershell
python main.py rebuild --metadata-only
```

完整重建索引：

```powershell
python main.py rebuild
```

## 注意事项

- `data/`、`logs/`、`.tmp/` 默认不会提交到 Git。
- FAISS 索引文件通常比较大，建议本地生成，不要提交到仓库。
- 如果你换了 HowToCook 数据、换了 embedding 模型，应该重新运行 `python main.py rebuild`。
