from cookqa.runtime import _load_ingredient_aliases


def test_runtime_loads_the_same_ingredient_aliases_as_build():
    aliases = _load_ingredient_aliases()

    assert aliases["西红柿"] == "番茄"
