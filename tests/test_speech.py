import io
from pathlib import Path

import pytest


def test_joins_nonempty_segments_in_order(tmp_path):
    from speech import transcribe_japanese

    class Segment:
        def __init__(self, text):
            self.text = text

    class Model:
        def transcribe(self, path, **kwargs):
            assert Path(path).suffix == '.wav'
            return iter([Segment('  昨日、'), Segment('友達と映画を見ました。'), Segment('')]), {'language': 'ja'}

    assert transcribe_japanese(Model(), io.BytesIO(b'RIFFtest'), '.wav', tmp_path) == '昨日、友達と映画を見ました。'


def test_rejects_empty_audio(tmp_path):
    from speech import transcribe_japanese
    with pytest.raises(ValueError, match='rỗng'):
        transcribe_japanese(object(), io.BytesIO(), '.wav', tmp_path)


def test_unsupported_suffix_is_rejected(tmp_path):
    from speech import transcribe_japanese
    with pytest.raises(ValueError, match='Định dạng'):
        transcribe_japanese(object(), io.BytesIO(b'audio'), '.exe', tmp_path)


@pytest.mark.parametrize('failure', [False, True])
def test_temp_recording_is_removed_after_success_and_failure(tmp_path, failure):
    from speech import transcribe_japanese

    class Model:
        def transcribe(self, path, **kwargs):
            if failure:
                raise RuntimeError('decoder failure')
            return iter([type('Segment', (), {'text': 'こんにちは。'})()]), {}

    if failure:
        with pytest.raises(RuntimeError):
            transcribe_japanese(Model(), io.BytesIO(b'audio'), '.webm', tmp_path)
    else:
        assert transcribe_japanese(Model(), io.BytesIO(b'audio'), '.webm', tmp_path) == 'こんにちは。'
    assert list(tmp_path.iterdir()) == []


def test_transcribe_forces_japanese_vad_and_beam_size_five(tmp_path):
    from speech import transcribe_japanese
    calls = []

    class Model:
        def transcribe(self, path, **kwargs):
            calls.append(kwargs)
            return iter([type('Segment', (), {'text': 'こんにちは。'})()]), {}

    transcribe_japanese(Model(), io.BytesIO(b'audio'), '.ogg', tmp_path)
    assert calls == [{'language': 'ja', 'task': 'transcribe', 'vad_filter': True, 'beam_size': 5}]


def test_transcriber_creates_missing_temp_directory(tmp_path):
    from speech import transcribe_japanese
    nested = tmp_path / 'transient'

    class Model:
        def transcribe(self, path, **kwargs):
            assert Path(path).parent == nested
            return iter([type('Segment', (), {'text': 'こんにちは。'})()]), {}

    assert transcribe_japanese(Model(), io.BytesIO(b'audio'), '.wav', nested) == 'こんにちは。'
    assert not nested.exists() or list(nested.iterdir()) == []


def test_installed_faster_whisper_decoder_accepts_wav(tmp_path):
    import importlib.util
    import struct
    import wave

    if importlib.util.find_spec('faster_whisper') is None:
        pytest.skip('Install requirements.txt to verify the faster-whisper/PyAV runtime pair')
    from faster_whisper.audio import decode_audio
    path = tmp_path / 'speech.wav'
    with wave.open(str(path), 'wb') as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(24000)
        output.writeframes(struct.pack('<h', 600) * 24000)
    decoded = decode_audio(str(path))
    assert len(decoded) >= 15000
