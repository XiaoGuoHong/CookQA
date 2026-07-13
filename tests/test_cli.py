from cookqa.cli import build_parser


def test_build_command_uses_versioned_mvp_defaults():
    args = build_parser().parse_args(["build-indexes"])

    assert args.source_root.as_posix().endswith("Data/source/howtocook")
    assert args.selection.as_posix().endswith("config/recipe-selection-mvp.txt")
    assert args.source_manifest.as_posix().endswith("config/howtocook-source.json")


def test_serve_command_binds_only_to_loopback_by_default():
    args = build_parser().parse_args(["serve"])

    assert args.host == "127.0.0.1"
    assert args.port == 8000
