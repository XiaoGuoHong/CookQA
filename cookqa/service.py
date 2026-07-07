import json
from pathlib import Path
from typing import Optional

from .config import CookQASettings
from .generation import AnswerGenerator
from .graph import RecipeGraph
from .index_store import FaissIndexStore, build_recipe_chunks, build_step_chunks
from .models import ChatResult, RecipeDocument, SourceRef
from .ollama_client import OllamaClient
from .parser import load_recipes
from .retrieval import RecipeRetriever


_DEFAULT_OLLAMA = object()


class CookQAService:
    def __init__(
        self,
        settings: CookQASettings,
        recipes: list[RecipeDocument],
        graph: RecipeGraph,
        recipe_index: Optional[FaissIndexStore],
        step_index: Optional[FaissIndexStore],
        ollama_client: Optional[OllamaClient],
    ):
        self.settings = settings
        self.recipes = {recipe.recipe_id: recipe for recipe in recipes}
        self.graph = graph
        self.recipe_index = recipe_index
        self.step_index = step_index
        self.ollama_client = ollama_client

    @classmethod
    def from_settings(
        cls,
        settings: CookQASettings,
        ollama_client: Optional[OllamaClient] | object = _DEFAULT_OLLAMA,
    ) -> "CookQAService":
        if ollama_client is _DEFAULT_OLLAMA:
            ollama_client = OllamaClient(
                settings.ollama_base_url,
                settings.embedding_model,
                settings.chat_model,
                timeout=settings.ollama_timeout,
            )
        recipes = cls._load_recipe_metadata(settings.parsed_recipes_path)
        graph = RecipeGraph.build(recipes)
        recipe_index = cls._load_index(
            settings.recipe_index_path,
            settings.recipe_payload_path,
        )
        step_index = cls._load_index(
            settings.step_index_path,
            settings.step_payload_path,
        )
        return cls(
            settings,
            recipes,
            graph,
            recipe_index,
            step_index,
            ollama_client,
        )

    @staticmethod
    def _load_recipe_metadata(path: Path) -> list[RecipeDocument]:
        if not path.exists():
            return []
        raw = json.loads(path.read_text(encoding="utf-8"))
        return [RecipeDocument(**item) for item in raw]

    @staticmethod
    def _load_index(
        index_path: Path,
        payload_path: Path,
    ) -> Optional[FaissIndexStore]:
        try:
            return FaissIndexStore.load(index_path, payload_path)
        except FileNotFoundError:
            return None

    def rebuild_metadata(self) -> dict[str, int]:
        recipes = load_recipes(self.settings.howtocook_path)
        self.settings.parsed_dir.mkdir(parents=True, exist_ok=True)
        self.settings.graph_dir.mkdir(parents=True, exist_ok=True)
        self.settings.parsed_recipes_path.write_text(
            json.dumps(
                [recipe.model_dump() for recipe in recipes],
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        graph = RecipeGraph.build(recipes)
        self.settings.graph_path.write_text(
            json.dumps(graph.relations, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self.recipes = {recipe.recipe_id: recipe for recipe in recipes}
        self.graph = graph
        return {"recipes": len(recipes), "relations": len(graph.relations)}

    def rebuild_indexes(self) -> dict[str, int]:
        self.rebuild_metadata()
        if self.ollama_client is None:
            raise RuntimeError("Ollama client is required to rebuild FAISS indexes")
        recipes = list(self.recipes.values())
        recipe_chunks = build_recipe_chunks(recipes)
        step_chunks = build_step_chunks(recipes)
        FaissIndexStore.build(
            recipe_chunks,
            self.ollama_client.embed_texts,
            self.settings.recipe_index_path,
            self.settings.recipe_payload_path,
        )
        FaissIndexStore.build(
            step_chunks,
            self.ollama_client.embed_texts,
            self.settings.step_index_path,
            self.settings.step_payload_path,
        )
        self.recipe_index = FaissIndexStore.load(
            self.settings.recipe_index_path,
            self.settings.recipe_payload_path,
        )
        self.step_index = FaissIndexStore.load(
            self.settings.step_index_path,
            self.settings.step_payload_path,
        )
        return {
            "recipes": len(recipes),
            "recipe_chunks": len(recipe_chunks),
            "step_chunks": len(step_chunks),
        }

    def search(self, question: str, top_k: int):
        retriever = RecipeRetriever(
            recipes=self.recipes.values(),
            graph=self.graph,
            recipe_index=self.recipe_index,
            step_index=self.step_index,
            embed_query=self.ollama_client.embed_query if self.ollama_client else None,
        )
        return retriever.search(question, top_k)

    def chat(self, question: str, top_k: int, include_steps: bool) -> ChatResult:
        mode, recommendations = self.search(question, top_k)
        if not include_steps:
            recommendations = [
                item.model_copy(update={"summary_steps": []}) for item in recommendations
            ]
        answer = AnswerGenerator(self.ollama_client).generate(
            question,
            mode,
            recommendations,
        )
        sources = [
            SourceRef(
                recipe_id=item.recipe_id,
                name=item.name,
                source_path=item.source_path,
                source_url=item.source_url,
            )
            for item in recommendations
        ]
        return ChatResult(
            answer=answer,
            mode=mode,
            recommendations=recommendations,
            sources=sources,
            metadata={"top_k": top_k},
        )

    def get_recipe(self, recipe_id: str) -> RecipeDocument:
        recipe = self.recipes.get(recipe_id)
        if recipe is None:
            raise KeyError(recipe_id)
        return recipe
