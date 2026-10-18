import runpy
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


@pytest.fixture
def pulse_backend(monkeypatch):
    volumes = {3: 0.427, 8: 0.75}
    descriptions = {3: 'Speakers', 8: 'Headphones'}

    def sink_info(index):
        return SimpleNamespace(
            index=index,
            description=descriptions[index],
            volume=SimpleNamespace(value_flat=volumes[index]),
        )

    def set_volume(sink, volume):
        volumes[sink.index] = volume

    def change_volume(sink, increment):
        volumes[sink.index] = max(0, sink.volume.value_flat + increment)

    pulse = Mock()
    pulse.sink_list.side_effect = lambda: [sink_info(index) for index in volumes]
    pulse.sink_info.side_effect = sink_info
    pulse.volume_set_all_chans.side_effect = set_volume
    pulse.volume_change_all_chans.side_effect = change_volume
    factory = Mock(return_value=pulse)
    monkeypatch.setitem(sys.modules, 'pulsectl', SimpleNamespace(Pulse=factory))
    module = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'cplay'))
    return SimpleNamespace(
        mixer_class=module['PulseMixer'], pulse=pulse, factory=factory,
        volumes=volumes,
    )


def test_initialization_does_not_change_volume(pulse_backend):
    mixer = pulse_backend.mixer_class()

    pulse_backend.factory.assert_called_once_with('cplay')
    assert mixer.get() == 42
    assert str(mixer) == 'volume 42% (Pulse Speakers)'
    pulse_backend.pulse.volume_set_all_chans.assert_not_called()


def test_get_refreshes_external_volume_changes(pulse_backend):
    mixer = pulse_backend.mixer_class()
    pulse_backend.volumes[3] = 0.65

    assert mixer.get() == 65


def test_set_uses_sink_object_and_percentage(pulse_backend):
    mixer = pulse_backend.mixer_class()
    mixer.set(37)

    assert pulse_backend.volumes[3] == pytest.approx(0.37)
    assert mixer.get() == 37


@pytest.mark.parametrize('increment', [1, -1, 0])
def test_cue_uses_current_volume(pulse_backend, increment):
    mixer = pulse_backend.mixer_class()
    pulse_backend.volumes[3] = 0.60
    mixer.cue(increment)

    assert pulse_backend.volumes[3] == pytest.approx(0.60 + increment / 100)


def test_toggle_changes_active_sink(pulse_backend):
    mixer = pulse_backend.mixer_class()
    mixer.toggle()

    assert mixer.get() == 75
    assert str(mixer) == 'volume 75% (Pulse Headphones)'
    mixer.set(20)
    mixer.cue(1)
    assert pulse_backend.volumes[8] == pytest.approx(0.21)
    assert pulse_backend.volumes[3] == 0.427
    mixer.toggle()
    assert mixer.get() == 42


@pytest.mark.parametrize('description', [None, '', 'Microphone', 'CAPTURE input'])
def test_no_usable_sinks_closes_connection(pulse_backend, description):
    pulse_backend.pulse.sink_list.side_effect = None
    pulse_backend.pulse.sink_list.return_value = [
        SimpleNamespace(description=description),
    ]

    with pytest.raises(ValueError, match='could not find pulse volume control'):
        pulse_backend.mixer_class()

    pulse_backend.pulse.close.assert_called_once_with()


def test_empty_sink_list(pulse_backend):
    pulse_backend.pulse.sink_list.side_effect = None
    pulse_backend.pulse.sink_list.return_value = []

    with pytest.raises(ValueError, match='could not find pulse volume control'):
        pulse_backend.mixer_class()

    pulse_backend.pulse.close.assert_called_once_with()


def test_close_disconnects(pulse_backend):
    mixer = pulse_backend.mixer_class()
    mixer.close()

    pulse_backend.pulse.close.assert_called_once_with()


def test_removed_sink_falls_back_to_remaining_output(pulse_backend):
    mixer = pulse_backend.mixer_class()
    del pulse_backend.volumes[3]

    mixer.cue(1)

    assert pulse_backend.volumes[8] == pytest.approx(0.76)
    assert str(mixer) == 'volume 76% (Pulse Headphones)'
    mixer.set(25)
    assert mixer.get() == 25


def test_all_sinks_removed_and_reconnected(pulse_backend):
    mixer = pulse_backend.mixer_class()
    pulse_backend.volumes.clear()

    assert mixer.get() == 0
    mixer.set(50)
    mixer.cue(1)
    mixer.toggle()
    assert str(mixer) == 'No PulseAudio output.'
    pulse_backend.pulse.volume_set_all_chans.assert_not_called()
    pulse_backend.pulse.volume_change_all_chans.assert_not_called()

    pulse_backend.volumes[8] = 0.75
    mixer.cue(1)
    assert str(mixer) == 'volume 76% (Pulse Headphones)'


def test_toggle_cycles_three_outputs(pulse_backend):
    mixer = pulse_backend.mixer_class()
    extra = SimpleNamespace(
        index=12, description='HDMI', volume=SimpleNamespace(value_flat=0.5),
    )
    sinks = pulse_backend.pulse.sink_list()
    pulse_backend.pulse.sink_list.side_effect = lambda: sinks + [extra]

    mixer.toggle()
    assert mixer.get() == 75
    mixer.toggle()
    assert mixer.get() == 50
    mixer.toggle()
    assert mixer.get() == 42
