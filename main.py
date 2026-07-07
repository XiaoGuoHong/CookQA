import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from cookqa.config import CookQASettings
from cookqa.service import CookQAService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CookQA 食神食谱问答")
    subparsers = parser.add_subparsers(dest="command", required=True)

    chat_parser = subparsers.add_parser("chat", help="Ask a cooking question")
    chat_parser.add_argument("question")
    chat_parser.add_argument("--top-k", type=int, default=5)
    chat_parser.add_argument("--no-steps", action="store_true")

    rebuild_parser = subparsers.add_parser(
        "rebuild",
        help="Rebuild metadata or vector indexes",
    )
    rebuild_parser.add_argument("--metadata-only", action="store_true")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    service = CookQAService.from_settings(CookQASettings.from_env())

    if args.command == "chat":
        result = service.chat(
            args.question,
            top_k=args.top_k,
            include_steps=not args.no_steps,
        )
        print(result.model_dump_json(indent=2))
        return

    if args.command == "rebuild":
        result = (
            service.rebuild_metadata()
            if args.metadata_only
            else service.rebuild_indexes()
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
