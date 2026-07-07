# CookQA 食神

CookQA is a FastAPI-first Chinese recipe GraphRAG service based on HowToCook,
FAISS, and Ollama.

## Features

- Parse HowToCook Markdown recipes.
- Build lightweight recipe graph relations.
- Build FAISS recipe and step indexes with Ollama `bge-m3`.
- Answer Chinese cooking questions with Ollama `gpt-oss:120b-cloud`.
- Return recommendation lists, match reasons, sources, and grounded answers.
- Run locally or with Docker.

## Local Setup

```powershell
pip install -r requirements.txt
$env:HOWTOCOOK_PATH="D:\path\to\HowToCook"
$env:OLLAMA_BASE_URL="http://127.0.0.1:11434"
python main.py rebuild
uvicorn api.app:app --host 127.0.0.1 --port 8000
```

## API Examples

```powershell
curl -X POST http://127.0.0.1:8000/api/v1/chat `
  -H "Content-Type: application/json" `
  -d "{\"question\":\"牛肉可以怎么做\",\"top_k\":5}"
```

## Docker

```powershell
docker compose up --build
```

The Docker image runs CookQA only. Ollama stays external and is configured by
`OLLAMA_BASE_URL`.
