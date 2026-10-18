import io
import runpy
from pathlib import Path
from unittest.mock import Mock

import pytest


@pytest.fixture
def module():
    return runpy.run_path(str(Path(__file__).resolve().parents[1] / 'cplay'))


@pytest.mark.parametrize('key', [ord('a'), 8, None])
def test_search_empty_playlist(module, monkeypatch, key):
    window = object.__new__(module['PlaylistWindow'])
    window.buffer = []
    app = Mock()
    monkeypatch.setitem(window.do_search.__globals__, 'APP', app)

    window.do_search(key)

    app.status.assert_called_once_with('List is empty', 1)


@pytest.mark.parametrize('command', [b'\n', b' \t\r\n', b''])
def test_fifo_ignores_empty_commands(module, command):
    control = object.__new__(module['FIFOControl'])
    control.fd = io.BytesIO(command)
    control.commands = Mock()

    control.handle_command()

    assert control.commands.mock_calls == []
