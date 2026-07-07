from typing import Protocol

from .models import QueryMode, Recommendation


class ChatClient(Protocol):
    def chat(self, prompt: str) -> str:
        ...


class AnswerGenerator:
    def __init__(self, chat_client: ChatClient | None):
        self.chat_client = chat_client

    def generate(
        self,
        question: str,
        mode: QueryMode,
        recommendations: list[Recommendation],
    ) -> str:
        if not recommendations:
            return "没有在 HowToCook 菜谱库中找到足够相关的菜谱。"

        prompt = self._build_prompt(question, mode, recommendations)
        if self.chat_client is not None:
            try:
                answer = self.chat_client.chat(prompt)
                if answer:
                    return answer
            except Exception:
                pass
        return self._fallback_answer(mode, recommendations)

    def _build_prompt(
        self,
        question: str,
        mode: QueryMode,
        recommendations: list[Recommendation],
    ) -> str:
        recipe_lines = []
        for item in recommendations:
            recipe_lines.append(
                "\n".join(
                    [
                        f"菜谱：{item.name}",
                        f"匹配原因：{item.match_reason}",
                        f"原料：{'、'.join(item.ingredients)}",
                        f"步骤摘要：{'；'.join(item.summary_steps)}",
                        f"来源：{item.source_path}",
                    ]
                )
            )
        context = "\n\n".join(recipe_lines)
        return (
            "你是中文做饭助手食神。只能根据给定菜谱回答，"
            "不要编造不存在的菜谱、食材、步骤、热量或难度。\n"
            f"用户问题：{question}\n"
            f"检索模式：{mode}\n"
            f"候选菜谱：\n{context}\n"
            "请先给推荐结论，再给最相关菜谱的简明做法。"
        )

    def _fallback_answer(
        self,
        mode: QueryMode,
        recommendations: list[Recommendation],
    ) -> str:
        names = "、".join(item.name for item in recommendations[:5])
        first = recommendations[0]
        steps = "；".join(first.summary_steps)
        if mode == "missing_or_fictional":
            prefix = "没有找到精确菜谱，下面是相近的 HowToCook 菜谱。"
        else:
            prefix = "当前未连接到可用的生成模型，先返回基于检索结果的答案。"
        return f"{prefix} 推荐：{names}。最相关的是 {first.name}，主要步骤：{steps}。"
