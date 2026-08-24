import pytest
from oddyssey_mcp import config


@pytest.fixture(autouse=True)
def _hermetic_config(tmp_path, monkeypatch):
    # The suite must never read the developer's real ~/.oddyssey/config.json:
    # tests that want specific values repoint CONFIG_PATH themselves and
    # override this default (monkeypatch is per-test, last set wins).
    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "config.json")
