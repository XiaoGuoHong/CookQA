from cookqa.generation import AnswerGenerator
from cookqa.models import Recommendation


class FailingChatClient:
    def chat(self, prompt: str) -> str:
        raise RuntimeError("ollama unavailable")


class StaticChatClient:
    def chat(self, prompt: str) -> str:
        assert "不要编造" in prompt
        return "可以做水煮牛肉，先腌制牛肉，再煮红汤。"


def recommendation():
    return Recommendation(
        recipe_id="dishes/meat_dish/水煮牛肉/水煮牛肉.md",
        name="水煮牛肉",
        score=0.91,
        match_reason="命中食材：牛肉",
        ingredients=["牛肉", "豆芽"],
        summary_steps=["腌制牛肉", "煮红汤"],
        source_path="dishes/meat_dish/水煮牛肉/水煮牛肉.md",
        graph_matches=["ingredient:牛肉"],
    )


def test_generator_uses_chat_client_when_available():
    answer = AnswerGenerator(StaticChatClient()).generate(
        "牛肉可以怎么做",
        "ingredient_exploration",
        [recommendation()],
    )

    assert "水煮牛肉" in answer


def test_generator_falls_back_when_chat_client_fails():
    answer = AnswerGenerator(FailingChatClient()).generate(
        "牛肉可以怎么做",
        "ingredient_exploration",
        [recommendation()],
    )

    assert "水煮牛肉" in answer
    assert "当前未连接到可用的生成模型" in answer
