import runpy
import signal
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


class EndRun(Exception):
    pass


@pytest.fixture
def playback(monkeypatch):
    module = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'cplay'))
    app = object.__new__(module['Application'])
    app.timeout = Mock()
    app.win_filelist = Mock()
    app.win_playlist = Mock()
    app.win_playlist.change_active_entry.return_value = None
    app.control = SimpleNamespace(fd=None)
    app.status = Mock()
    app.progress = Mock()
    app.counter = Mock()
    app.set_default_status = Mock()
    players = [module['Player'](f'player{i} %d %s', extension)
               for i, extension in enumerate([r'\.ogg$', r'\.mp3$', r'\.ogg$'])]
    app.player = players[0]
    monkeypatch.setitem(app.play.__globals__, 'APP', app)
    monkeypatch.setitem(app.play.__globals__, 'PLAYERS', players)
    monkeypatch.setitem(app.play.__globals__, 'which', lambda name: name)
    monkeypatch.setattr('select.select', Mock(side_effect=EndRun))
    entry = SimpleNamespace(pathname='track.ogg', offset=12, vp=lambda: 'track')
    return SimpleNamespace(app=app, players=players, entry=entry, module=module)


def process(returncode):
    return Mock(returncode=returncode, poll=Mock(return_value=returncode))


@pytest.mark.parametrize('returncode', [1, -signal.SIGTERM])
def test_failed_player_tries_next_matching_player(playback, monkeypatch, returncode):
    start = Mock(side_effect=[process(returncode), process(None)])
    monkeypatch.setattr('subprocess.Popen', start)
    playback.app.play(playback.entry)

    with pytest.raises(EndRun):
        playback.app.run()

    assert [call.args[0] for call in start.call_args_list] == [
        ['player0', '12', 'track.ogg'], ['player2', '12', 'track.ogg'],
    ]
    assert playback.app.player is playback.players[2]
    playback.app.win_playlist.change_active_entry.assert_not_called()


def test_launch_failure_tries_next_matching_player(playback, monkeypatch):
    start = Mock(side_effect=[OSError('cannot execute'), process(None)])
    monkeypatch.setattr('subprocess.Popen', start)

    assert playback.app.play(playback.entry)
    assert playback.app.player is playback.players[2]
    assert start.call_count == 2


@pytest.mark.parametrize('returncode', [0, 1])
def test_completion_or_exhausted_fallback_advances_playlist(
        playback, monkeypatch, returncode):
    start = Mock(side_effect=lambda *args, **kwargs: process(returncode))
    monkeypatch.setattr('subprocess.Popen', start)
    playback.app.play(playback.entry)

    with pytest.raises(EndRun):
        playback.app.run()

    assert start.call_count == (1 if returncode == 0 else 2)
    playback.app.win_playlist.change_active_entry.assert_called_once_with(1)
    assert playback.app.player.stopped


def test_next_track_starts_from_first_player(playback, monkeypatch):
    start = Mock(side_effect=[process(1), process(1), process(None)])
    monkeypatch.setattr('subprocess.Popen', start)
    next_entry = SimpleNamespace(pathname='next.ogg', offset=0, vp=lambda: 'next')
    playback.app.win_playlist.change_active_entry.return_value = next_entry
    playback.app.play(playback.entry)

    with pytest.raises(EndRun):
        playback.app.run()

    assert start.call_args.args[0] == ['player0', '0', 'next.ogg']


def test_missing_players_are_skipped(playback, monkeypatch):
    monkeypatch.setitem(playback.app.play.__globals__, 'which',
                        lambda name: None if name == 'player0' else name)
    start = Mock(return_value=process(None))
    monkeypatch.setattr('subprocess.Popen', start)

    assert playback.app.play(playback.entry)
    assert playback.app.player is playback.players[2]
    start.assert_called_once()


def test_no_available_player_advances_playlist(playback, monkeypatch):
    monkeypatch.setitem(playback.app.play.__globals__, 'which', lambda name: None)

    assert not playback.app.play(playback.entry)
    with pytest.raises(EndRun):
        playback.app.run()

    playback.app.win_playlist.change_active_entry.assert_called_once_with(1)


def test_manual_stop_does_not_try_another_player(playback, monkeypatch):
    start = Mock(return_value=process(None))
    monkeypatch.setattr('subprocess.Popen', start)
    playback.app.play(playback.entry)
    playback.app.player.stop()

    with pytest.raises(EndRun):
        playback.app.run()

    start.assert_called_once()
    playback.app.win_playlist.change_active_entry.assert_not_called()


@pytest.mark.parametrize('returncode', [0, 3])
def test_poll_preserves_actual_exit_status(playback, returncode):
    player = playback.players[0]
    with subprocess.Popen([sys.executable, '-c', f'raise SystemExit({returncode})']) as proc:
        proc.wait(timeout=5)
        player._proc = proc

        assert player.poll() is playback.module['TERMINATED']

    assert player.returncode == returncode
    assert player._proc is None
