from pathlib import Path


def test_integration_tests_are_registered_and_excluded_by_default():
    config = Path("pytest.ini").read_text(encoding="utf-8")

    assert 'addopts = -m "not integration"' in config
    assert "integration: requires a running CookQA service" in config
