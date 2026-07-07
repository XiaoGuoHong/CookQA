from pathlib import Path

from cookqa.index_store import FaissIndexStore, build_recipe_chunks, build_step_chunks
from cookqa.parser import load_recipes


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "howtocook"


def fake_embed_texts(texts):
    vectors = []
    for text in texts:
        vectors.append(
            [
                1.0 if "牛肉" in text else 0.0,
                1.0 if "西红柿" in text else 0.0,
                1.0 if "鸡蛋" in text else 0.0,
            ]
        )
    return vectors


def fake_embed_query(text):
    return fake_embed_texts([text])[0]


def test_build_recipe_and_step_chunks():
    recipes = load_recipes(FIXTURE_ROOT)

    recipe_chunks = build_recipe_chunks(recipes)
    step_chunks = build_step_chunks(recipes)

    assert {chunk.kind for chunk in recipe_chunks} == {"recipe"}
    assert {chunk.kind for chunk in step_chunks} == {"step"}
    assert any(chunk.name == "水煮牛肉" for chunk in recipe_chunks)
    assert any("红汤" in chunk.text for chunk in step_chunks)


def test_faiss_store_searches_payloads(tmp_path):
    recipes = load_recipes(FIXTURE_ROOT)
    chunks = build_recipe_chunks(recipes)
    index_path = tmp_path / "recipes.faiss"
    payload_path = tmp_path / "recipes.payload.json"

    FaissIndexStore.build(chunks, fake_embed_texts, index_path, payload_path)
    store = FaissIndexStore.load(index_path, payload_path)
    results = store.search("牛肉可以怎么做", fake_embed_query, top_k=1)

    assert results[0][0].name == "水煮牛肉"
    assert results[0][1] > 0
