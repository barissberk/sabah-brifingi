"""Yerel medya sunucusu: yalnızca ses/video dosyaları, yalnızca bu bilgisayar, klasör listesi yok."""
from __future__ import annotations

import socket
import urllib.error
import urllib.request

import pytest

from agents import media_server
from config import Settings


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def server(tmp_path):
    s = Settings()
    s.output_dir = tmp_path
    s.media_server_port = free_port()
    day = tmp_path / "2026-10-10"
    day.mkdir()
    (day / "briefing_audio.mp3").write_bytes(b"ID3audio")
    (day / "briefing.json").write_text("{}", encoding="utf-8")
    srv = media_server.start_in_background(s)
    yield f"http://127.0.0.1:{s.media_server_port}"
    srv.shutdown()


def status(url: str) -> int:
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def test_serves_audio(server):
    with urllib.request.urlopen(f"{server}/2026-10-10/briefing_audio.mp3", timeout=5) as r:
        assert r.status == 200 and r.read() == b"ID3audio"
        assert r.headers["Content-Type"] == "audio/mpeg"


def test_blocks_other_files_and_listing(server):
    assert status(f"{server}/2026-10-10/briefing.json") == 404
    assert status(f"{server}/2026-10-10/") == 404
    assert status(f"{server}/../config.py") == 404


def test_binds_to_localhost_only(tmp_path):
    s = Settings()
    s.output_dir, s.media_server_port = tmp_path, free_port()
    srv = media_server.make_server(s)
    try:
        assert srv.server_address[0] == "127.0.0.1"
    finally:
        srv.server_close()
