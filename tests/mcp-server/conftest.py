import pytest
from oddyssey_mcp import config, stack


@pytest.fixture(autouse=True)
def _hermetic_config(tmp_path, monkeypatch):
    # The suite must never read the developer's real ~/.oddyssey/config.json,
    # nor shell out to docker for the running container's ports: tests that
    # want specific values repoint CONFIG_PATH / _container_host_ports
    # themselves and override these defaults (monkeypatch is per-test, last
    # set wins).
    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "config.json")
    monkeypatch.setattr(stack, "_container_host_ports", lambda: None)
