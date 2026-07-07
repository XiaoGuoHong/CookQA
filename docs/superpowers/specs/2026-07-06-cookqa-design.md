# CookQA Design

## Background

CookQA, Chinese product name "食神", is a local recipe RAG project built from the
open-source HowToCook dataset. The target user asks natural Chinese cooking
questions such as "牛肉可以怎么做", "番茄炒蛋怎么做", or "黯然销魂饭怎么做".
The system should recommend relevant recipes, explain why they match, and give a
grounded cooking answer from retrieved recipe sources.

The project will reuse the existing `CookQA` folder. The previous BaseQA code in
that folder can be replaced because it was an unrelated customer-service QA
prototype.

## Goals

- Build a FastAPI-first backend that can later support a Web UI without changing
  the core RAG pipeline.
- Support Docker deployment for the FastAPI service.
- Ingest Markdown recipes from `Anduin2017/HowToCook`.
- Parse recipes into structured records: name, category, ingredients, tools,
  difficulty, calories, steps, notes, source path, and source URL when available.
- Build FAISS indexes with the local Ollama `bge-m3` embedding model.
- Build a lightweight graph layer for recipe relations such as ingredient,
  category, cooking method, flavor, and tool.
- Use local Ollama `gpt-oss:120b-cloud` for answer composition, not for inventing
  unsupported recipes.
- Return both recommendation lists and chat-style answers from the main API.

## Non-Goals For The First Version

- No full Web frontend in the first slice.
- No Neo4j or external graph database.
- No user accounts, favorites, comments, or ratings.
- No nutrition claims beyond values explicitly parsed from source recipes.
- No generated recipe hallucination when the source dataset does not contain a
  matching recipe.
- No Docker image that embeds Ollama models. Ollama remains an external runtime
  dependency configured by URL.

## Product Behavior

CookQA should classify the user's intent into broad retrieval modes:

- Dish lookup: "番茄炒蛋怎么做" should find the exact or near-exact recipe and
  expand its ingredients and steps.
- Ingredient exploration: "牛肉可以怎么做" should recommend several recipes that
  use beef, with match reasons and concise summaries.
- Missing or fictional dish: "黯然销魂饭怎么做" should state when no exact recipe
  exists in HowToCook, then recommend the closest supported recipes if retrieval
  finds reasonable alternatives.
- Follow-up-friendly answer: API responses should include recipe IDs and sources
  so a future Web chat can ask follow-up questions without redoing all context
  assembly.

## Architecture

The first version uses one FastAPI service with separated internal modules:

1. Data ingestion reads a local clone or downloaded copy of HowToCook.
2. Markdown parsing converts recipe files into `RecipeDocument` records.
3. Graph building stores local relation files for recipe-to-ingredient,
   recipe-to-category, recipe-to-method, recipe-to-flavor, and recipe-to-tool
   edges.
4. Embedding builds FAISS indexes for recipe-level retrieval and step-level
   retrieval in the first implementation.
5. Retrieval combines lexical matching, graph relation matching, and FAISS
   semantic search.
6. Ranking merges those signals into recommendations with transparent match
   reasons.
7. Answer generation passes only retrieved context to `gpt-oss:120b-cloud` and
   asks it to produce a concise grounded Chinese answer.
8. FastAPI returns structured JSON that can be consumed by CLI tests, API
   clients, or a future Web frontend.

## Components

### Configuration

Configuration lives in a project config file and environment variables. Required
settings include:

- HowToCook source path or Git URL.
- Data directory for parsed recipes, graph relations, and FAISS index files.
- Ollama base URL.
- Embedding model name, default `bge-m3`.
- Chat model name, default `gpt-oss:120b-cloud`.
- Retrieval defaults such as `top_k`, score thresholds, and max context size.
- Docker-facing paths for mounted data, indexes, logs, and optional HowToCook
  source files.

### Recipe Parser

The parser walks HowToCook Markdown files under `dishes/` and optionally `tips/`.
For dish recipes, it extracts sections by Markdown headings. It should tolerate
minor format differences and preserve the raw Markdown for source-grounded
fallbacks.

Every parsed recipe receives a stable ID derived from its relative path. That ID
is used across metadata JSON, FAISS payloads, graph edges, and API responses.

### Lightweight Graph

The graph layer is local and file-backed in the first version. It does not need a
graph database because the initial relationship queries are simple adjacency
lookups.

Example relations:

- `ingredient:牛肉 -> recipe:水煮牛肉`
- `category:荤菜 -> recipe:水煮牛肉`
- `method:炖 -> recipe:西红柿土豆炖牛肉`
- `tool:空气炸锅 -> recipe:空气炸锅脆皮现腌炸鸡`

Graph matching is used to improve ingredient and constraint queries, not to
replace semantic search.

### FAISS Retrieval

The first implementation builds two index granularities:

- Recipe index: one vector per recipe summary record, useful for broad queries.
- Step index: one vector per operation or section chunk, useful for "怎么做" and
  follow-up questions.

Both indexes are part of the first usable product slice because the user wants
recommendation lists and direct "怎么做" answers.

### Answer Generation

The generator receives ranked recommendations and selected source snippets. It
must follow these rules:

- Answer in Chinese.
- Prefer exact recipe matches when available.
- Include multiple recommendations for broad ingredient questions.
- Say clearly when no exact recipe is found.
- Do not invent ingredients, steps, calories, or difficulty.
- Include source recipe names in the response.

If Ollama is unavailable, the API should still return recommendations and a
template-based answer explaining that generation is unavailable.

### Docker Deployment

The project should include a Dockerfile and a docker-compose file for local
deployment. The container runs only the CookQA FastAPI service. Ollama is
configured through `OLLAMA_BASE_URL`, so deployment can target either the user's
host Ollama service or a separately managed Ollama container.

Runtime data is mounted as volumes:

- HowToCook source or fixture data.
- Parsed recipe metadata.
- FAISS index files.
- Graph relation files.
- Logs.

The container image should install Python dependencies, expose the FastAPI port,
and start Uvicorn. It should not rebuild indexes automatically on every startup;
index rebuild remains an explicit command or API call so container restarts are
fast and predictable.

## API Design

### `POST /api/v1/chat`

Main product endpoint.

Request:

```json
{
  "question": "牛肉可以怎么做",
  "top_k": 5,
  "include_steps": true
}
```

Response:

```json
{
  "answer": "可以优先考虑水煮牛肉、西红柿土豆炖牛肉、黑椒牛柳...",
  "mode": "ingredient_exploration",
  "recommendations": [
    {
      "recipe_id": "dishes/meat_dish/水煮牛肉/水煮牛肉.md",
      "name": "水煮牛肉",
      "score": 0.91,
      "match_reason": "命中食材：牛肉；类别：荤菜；语义相似度高",
      "ingredients": ["牛肉", "豆芽", "鸡蛋", "豆瓣酱"],
      "summary_steps": ["腌制牛肉", "煮红汤", "焯豆芽", "煮牛肉", "泼热油"],
      "source_path": "dishes/meat_dish/水煮牛肉/水煮牛肉.md"
    }
  ],
  "sources": [
    {
      "recipe_id": "dishes/meat_dish/水煮牛肉/水煮牛肉.md",
      "name": "水煮牛肉",
      "source_path": "dishes/meat_dish/水煮牛肉/水煮牛肉.md"
    }
  ]
}
```

### `GET /api/v1/recipes/search`

Debuggable search endpoint. It returns ranked recipe records without LLM answer
generation.

### `GET /api/v1/recipes/{recipe_id}`

Returns one parsed recipe with full structured fields and raw source text.

### `POST /api/v1/index/rebuild`

Rebuilds parsed metadata, graph relations, and FAISS indexes from the configured
HowToCook source.

## Data Flow

```text
HowToCook Markdown
  -> parse recipe documents
  -> write normalized recipe metadata
  -> build graph relation files
  -> embed recipe and step texts with Ollama bge-m3
  -> write FAISS indexes and payload metadata
  -> FastAPI loads indexes at startup
  -> user question
  -> query classification and retrieval
  -> graph + lexical + vector ranking
  -> gpt-oss answer generation with retrieved context
  -> structured JSON response
```

## Error Handling

- Missing HowToCook data: return a clear setup error and keep `/health` alive.
- Parser failures: skip the bad file, record the error, and continue indexing.
- FAISS index missing: API returns an index-not-built error with rebuild guidance.
- Ollama embedding unavailable during rebuild: fail rebuild with model and URL
  details.
- Ollama chat unavailable during query: return recommendations with a fallback
  non-LLM answer.
- No exact match: state that the exact recipe was not found and return closest
  supported alternatives when confidence is sufficient.

## Testing Strategy

Tests should cover:

- Markdown parser extraction for representative HowToCook files.
- Stable recipe ID generation from relative paths.
- Graph relation building from parsed ingredients and categories.
- Retrieval behavior for "牛肉可以怎么做", "番茄炒蛋怎么做", and "黯然销魂饭怎么做".
- API response schemas for chat, search, recipe detail, rebuild, and health.
- Ollama failure fallback without requiring live model calls in unit tests.
- Docker build configuration for import/startup sanity where practical.

Integration tests can use a tiny fixture dataset with two or three recipe
Markdown files. Live Ollama and full HowToCook indexing should be optional
developer checks, not required for every unit test run.

## Migration From Existing CookQA

The existing `CookQA` folder contains a previous BaseQA prototype. The new
implementation can replace it because the user confirmed it is no longer needed.
Useful concepts to keep are the FastAPI entrypoint, test layout, configuration
idea, and separation between routing and service logic. The FAQ-specific modules,
customer-service data, and old README content should be removed or rewritten.

The local folder is not currently a Git repository. Before committing or pushing,
initialize it as a repository or replace it with a clone of
`https://github.com/XiaoGuoHong/CookQA.git`, then bind the implementation to that
remote.

## First Implementation Choices

- HowToCook source loading uses a configured local path first. A developer
  command may clone or refresh `Anduin2017/HowToCook`, but normal tests use local
  fixtures and do not require network access.
- The first implementation includes both recipe-level and step-level FAISS
  indexes.
- `POST /api/v1/index/rebuild` is enabled for local development. Production-style
  deployment should disable or protect it with configuration.
- Docker deployment is part of the first implementation. Ollama is external and
  configured by URL; model files are not copied into the app image.
