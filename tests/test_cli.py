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
