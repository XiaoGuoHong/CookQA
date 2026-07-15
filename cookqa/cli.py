from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
from pathlib import Path

from cookqa.config import Settings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cookqa", description="CookQA 本地 Graph RAG")
    subcommands = parser.add_subparsers(dest="command", required=True)

    build = subcommands.add_parser("build-indexes", help="构建并验证三套菜谱索引")
    build.add_argument("--source-root", type=Path, default=Path("Data/source/howtocook"))
    build.add_argument("--selection", type=Path, default=Path("config/recipe-selection-mvp.txt"))
    build.add_argument("--aliases", type=Path, default=Path("config/ingredient_aliases.json"))
    build.add_argument("--source-manifest", type=Path, default=Path("config/howtocook-source.json"))
    build.add_argument("--data-dir", type=Path, default=Path("Data"))

    rollback = subcommands.add_parser("rollback-indexes", help="验证并回滚到上一索引版本")
    rollback.add_argument("--data-dir", type=Path, default=Path("Data"))

    cleanup = subcommands.add_parser("cleanup-indexes", help="预览或执行历史索引清理")
    cleanup.add_argument("--data-dir", type=Path, default=Path("Data"))
    cleanup.add_argument("--keep", action="append", default=[], metavar="VERSION")
    cleanup.add_argument("--apply", action="store_true", help="执行已规划的删除；默认仅预览")

    serve = subcommands.add_parser("serve", help="启动本地 FastAPI 服务")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    return parser


def _source_version(source_root: Path, source_manifest: Path) -> str:
    pinned = json.loads(source_manifest.read_text(encoding="utf-8"))["commit"]
    try:
        actual = subprocess.run(
            ["git", "-C", str(source_root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError("无法读取 HowToCook Git 提交版本") from exc
    if actual != pinned:
        raise RuntimeError(f"HowToCook 提交不一致，期望 {pinned}，实际 {actual}")
    return actual


def _require_neo4j_password(settings: Settings) -> None:
    if not settings.neo4j_password:
        raise RuntimeError("缺少 NEO4J_PASSWORD，不能操作 Neo4j 图索引")


async def _build(args: argparse.Namespace) -> None:
    settings = Settings.from_env()
    _require_neo4j_password(settings)
    from neo4j import GraphDatabase

    from cookqa.generation.ollama import OllamaClient
    from cookqa.indexing.builder import BuildPipeline
    from cookqa.indexing.neo4j_writer import Neo4jGraphWriter

    source_version = _source_version(args.source_root, args.source_manifest)
    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )
    try:
        await asyncio.to_thread(driver.verify_connectivity)
        result = await BuildPipeline(
            OllamaClient(settings),
            Neo4jGraphWriter(driver),
        ).build(
            source_root=args.source_root,
            selection_path=args.selection,
            aliases_path=args.aliases,
            source_version=source_version,
            embedding_model=settings.embedding_model,
            data_dir=args.data_dir,
        )
    finally:
        driver.close()
    _print_result(result)


async def _rollback(args: argparse.Namespace) -> None:
    settings = Settings.from_env()
    _require_neo4j_password(settings)
    from neo4j import GraphDatabase

    from cookqa.generation.ollama import OllamaClient
    from cookqa.indexing.builder import BuildPipeline
    from cookqa.indexing.neo4j_writer import Neo4jGraphWriter

    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )
    try:
        await asyncio.to_thread(driver.verify_connectivity)
        result = await BuildPipeline(
            OllamaClient(settings),
            Neo4jGraphWriter(driver),
        ).rollback(args.data_dir)
    finally:
        driver.close()
    _print_result(result)


async def _cleanup(args: argparse.Namespace) -> None:
    settings = Settings.from_env()
    _require_neo4j_password(settings)
    from neo4j import GraphDatabase

    from cookqa.indexing.builder import BuildPipeline
    from cookqa.indexing.neo4j_writer import Neo4jGraphWriter

    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )
    try:
        await asyncio.to_thread(driver.verify_connectivity)
        result = await BuildPipeline(
            embedder=None,
            graph_writer=Neo4jGraphWriter(driver),
        ).cleanup_history(
            args.data_dir,
            explicit_keep=set(args.keep),
            apply=args.apply,
        )
    finally:
        driver.close()
    print(
        json.dumps(
            {"status": "ok", "dry_run": not args.apply, **result.as_dict()},
            ensure_ascii=False,
        )
    )


def _print_result(result) -> None:
    print(
        json.dumps(
            {
                "status": "ok",
                "version": result.manifest.data_version,
                "recipe_count": result.manifest.recipe_count,
                "artifact_dir": str(result.artifact_dir),
            },
            ensure_ascii=False,
        )
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "build-indexes":
        asyncio.run(_build(args))
        return 0
    if args.command == "rollback-indexes":
        asyncio.run(_rollback(args))
        return 0
    if args.command == "cleanup-indexes":
        asyncio.run(_cleanup(args))
        return 0
    if args.command == "serve":
        import uvicorn

        uvicorn.run("api.app:app", host=args.host, port=args.port, reload=False)
        return 0
    raise AssertionError(f"未知命令: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
