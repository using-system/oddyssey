from pathlib import Path

import httpx
from oddyssey_mcp.stack import compose_file, stack_status

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_packaged_compose_matches_repo_copy(monkeypatch):
    monkeypatch.delenv("ODD_COMPOSE_FILE", raising=False)
    packaged = compose_file().read_text()
    canonical = (REPO_ROOT / "docker-compose" / "docker-compose.yml").read_text()
    assert packaged == canonical, (
        "src/mcp-server/app/resources/docker-compose.yml drifted from "
        "docker-compose/docker-compose.yml — keep both copies identical"
    )


def test_compose_file_env_override(tmp_path, monkeypatch):
    override = tmp_path / "custom.yml"
    override.write_text("services: {}\n")
    monkeypatch.setenv("ODD_COMPOSE_FILE", str(override))
    assert compose_file() == override


def test_stack_status_all_ready():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200)

    status = stack_status(transport=httpx.MockTransport(handler))
    assert status == {"running": True, "prometheus": True, "tempo": True}


def test_stack_status_down_is_not_an_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    status = stack_status(transport=httpx.MockTransport(handler))
    assert status == {"running": False, "prometheus": False, "tempo": False}
