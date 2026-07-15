from pathlib import Path

import cookqa.cli as cli


def test_rollback_command_dispatches_to_async_handler(tmp_path, monkeypatch):
    called = {}

    async def fake_rollback(args):
        called["data_dir"] = args.data_dir

    monkeypatch.setattr(cli, "_rollback", fake_rollback, raising=False)

    result = cli.main(["rollback-indexes", "--data-dir", str(tmp_path)])

    assert result == 0
    assert called["data_dir"] == Path(tmp_path)


def test_cleanup_command_defaults_to_dry_run(tmp_path, monkeypatch):
    called = {}

    async def fake_cleanup(args):
        called["data_dir"] = args.data_dir
        called["keep"] = args.keep
        called["apply"] = args.apply

    monkeypatch.setattr(cli, "_cleanup", fake_cleanup, raising=False)

    result = cli.main(["cleanup-indexes", "--data-dir", str(tmp_path)])

    assert result == 0
    assert called == {
        "data_dir": Path(tmp_path),
        "keep": [],
        "apply": False,
    }


def test_cleanup_command_accepts_repeatable_keep_and_explicit_apply(
    tmp_path, monkeypatch
):
    called = {}

    async def fake_cleanup(args):
        called["keep"] = args.keep
        called["apply"] = args.apply

    monkeypatch.setattr(cli, "_cleanup", fake_cleanup, raising=False)

    result = cli.main(
        [
            "cleanup-indexes",
            "--data-dir",
            str(tmp_path),
            "--keep",
            "v1",
            "--keep",
            "v0",
            "--apply",
        ]
    )

    assert result == 0
    assert called == {"keep": ["v1", "v0"], "apply": True}
