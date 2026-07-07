import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class CookQASettings:
    project_root: Path
    data_dir: Path
    howtocook_path: Path
    ollama_base_url: str
    embedding_model: str
    chat_model: str
    top_k: int
    min_score: float
    enable_rebuild_api: bool

    @classmethod
    def from_env(cls) -> "CookQASettings":
        data_dir = Path(os.getenv("COOKQA_DATA_DIR", PROJECT_ROOT / "data")).resolve()
        return cls(
            project_root=PROJECT_ROOT,
            data_dir=data_dir,
            howtocook_path=Path(
                os.getenv("HOWTOCOOK_PATH", data_dir / "HowToCook")
            ).resolve(),
            ollama_base_url=os.getenv(
                "OLLAMA_BASE_URL", "http://127.0.0.1:11434"
            ).rstrip("/"),
            embedding_model=os.getenv("OLLAMA_EMBEDDING_MODEL", "bge-m3"),
            chat_model=os.getenv("OLLAMA_CHAT_MODEL", "gpt-oss:120b-cloud"),
            top_k=int(os.getenv("COOKQA_TOP_K", "5")),
            min_score=float(os.getenv("COOKQA_MIN_SCORE", "0.15")),
            enable_rebuild_api=os.getenv(
                "COOKQA_ENABLE_REBUILD_API", "true"
            ).lower()
            in {"1", "true", "yes", "on"},
        )

    @property
    def parsed_dir(self) -> Path:
        return self.data_dir / "parsed"

    @property
    def graph_dir(self) -> Path:
        return self.data_dir / "graph"

    @property
    def index_dir(self) -> Path:
        return self.data_dir / "indexes"

    @property
    def parsed_recipes_path(self) -> Path:
        return self.parsed_dir / "recipes.json"

    @property
    def graph_path(self) -> Path:
        return self.graph_dir / "relations.json"

    @property
    def recipe_index_path(self) -> Path:
        return self.index_dir / "recipes.faiss"

    @property
    def recipe_payload_path(self) -> Path:
        return self.index_dir / "recipes.payload.json"

    @property
    def step_index_path(self) -> Path:
        return self.index_dir / "steps.faiss"

    @property
    def step_payload_path(self) -> Path:
        return self.index_dir / "steps.payload.json"
