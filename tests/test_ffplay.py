import runpy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


@pytest.fixture
def player(monkeypatch):
    module = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'cplay'))
    monkeypatch.setitem(module['Player'].setup.__globals__, 'APP', Mock())
    result = module['FFPlay']('ffplay -ss %d %s', r'.*')
    result.tid = 1
    return result


DURATION = b'  Duration: 01:03:42.50, start: 0.000000\n'


@pytest.mark.parametrize('boundary', range(1, len(DURATION)))
def test_duration_split_across_reads(player, monkeypatch, boundary):
    read = Mock(side_effect=[DURATION[:boundary], DURATION[boundary:]])
    monkeypatch.setattr('os.read', read)

    player.read_fd(0)
    player.read_fd(0)

    assert player.length == 3822


def test_duration_split_across_many_reads(player, monkeypatch):
    monkeypatch.setattr('os.read', Mock(side_effect=[bytes([c]) for c in DURATION]))

    for _ in DURATION:
        player.read_fd(0)

    assert player.length == 3822
    assert player._duration_buf == b''


@pytest.mark.parametrize('offset', [0, 30])
def test_setup_discards_previous_partial_line(player, monkeypatch, offset):
    monkeypatch.setattr('os.read', Mock(side_effect=[b'Duration: 00:', b'03:42.50\n']))
    monkeypatch.setitem(player.setup.__globals__, 'which', lambda name: name)
    entry = SimpleNamespace(pathname='track.ogg')
    player.read_fd(0)

    assert player.setup(entry, offset) == 'ffplay'
    assert player._duration_buf == b''
    player.read_fd(0)
    assert player.length == 0


def test_duration_buffer_does_not_replace_progress_buffer(player, monkeypatch):
    progress = b'  12.50 M-A: 0.000\r'
    monkeypatch.setattr('os.read', Mock(side_effect=[DURATION, progress]))
    player.show_position = Mock()
    player.read_fd(0)
    player.read_fd(0)
    player.parse_buf()

    assert player.buf == progress
    assert player.offset == 12
    assert player.length == 3822
    player.show_position.assert_called_once_with()


def test_unterminated_output_does_not_grow_buffer_indefinitely(player, monkeypatch):
    monkeypatch.setattr('os.read', Mock(return_value=b'x' * 512))

    for _ in range(20):
        player.read_fd(0)

    assert len(player._duration_buf) <= 512
