import asyncio
import json
from pathlib import Path

import faiss

from cookqa.indexing.builder import BuildPipeline

FIXTURE = Path(__file__).parent / "fixtures" / "howtocook" / "sample.md"


class FakeEmbedder:
    async def embed(self, text):
        return [1.0, float(len(text) % 7 + 1)]


class FakeGraphWriter:
    def __init__(self):
        self.ids = set()

    async def replace_recipes(self, recipes, data_version):
        self.ids = {recipe.recipe_id for recipe in recipes}
        return self.ids


def test_builder_activates_only_validated_artifacts(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "sample.md").write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    selection = tmp_path / "selection.txt"
    selection.write_text("sample.md\n", encoding="utf-8")
    aliases = tmp_path / "aliases.json"
    aliases.write_text('{"西红柿": "番茄"}', encoding="utf-8")
    data_dir = tmp_path / "Data"
    graph_writer = FakeGraphWriter()

    result = asyncio.run(
        BuildPipeline(FakeEmbedder(), graph_writer).build(
            source_root=source,
            selection_path=selection,
            aliases_path=aliases,
            source_version="abc123",
            embedding_model="bge-m3",
            data_dir=data_dir,
        )
    )

    active = json.loads((data_dir / "runtime" / "active.json").read_text(encoding="utf-8"))
    index_path = result.artifact_dir / "faiss.index"
    ids_path = result.artifact_dir / "faiss.ids.json"
    assert active["version"] == result.manifest.data_version
    assert (result.artifact_dir / "bm25.json").is_file()
    assert index_path.is_file()
    assert ids_path.is_file()
    assert faiss.read_index(str(index_path)).ntotal == 1
    assert json.loads(ids_path.read_text(encoding="utf-8")) == list(graph_writer.ids)
    assert (data_dir / "processed" / "recipes.jsonl").is_file()
    assert result.manifest.recipe_count == 1
