"""Local Japanese speech-to-text adapter.

The faster-whisper import is lazy so typed chat can run when the optional
speech dependency or model is unavailable.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import BinaryIO

SUPPORTED_SUFFIXES = {'.webm', '.ogg', '.wav', '.mp4'}


class SpeechTranscriber:
    """Small wrapper that keeps the model dependency injectable in tests."""

    def __init__(self, model):
        self.model = model

    def transcribe(self, path: str, **kwargs):
        return self.model.transcribe(path, **kwargs)


def load_transcriber(model_name: str, device: str, compute_type: str, download_root: Path) -> SpeechTranscriber:
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError('Chưa cài faster-whisper. Hãy cài requirements.txt để dùng microphone.') from exc
    download_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    model = WhisperModel(model_name, device=device, compute_type=compute_type,
                         download_root=str(download_root))
    return SpeechTranscriber(model)


def transcribe_japanese(transcriber, audio: BinaryIO, suffix: str, temp_dir: Path | None = None) -> str:
    """Decode a bounded recording and return non-empty Japanese transcript text."""
    suffix = suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise ValueError('Định dạng audio không được hỗ trợ.')
    content = audio.read()
    if not content:
        raise ValueError('File audio rỗng.')
    directory = Path(temp_dir) if temp_dir is not None else None
    if directory is not None:
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = tempfile.NamedTemporaryFile(prefix='voice-', suffix=suffix, dir=directory,
                                             delete=False)
    path = Path(temporary.name)
    try:
        with temporary:
            temporary.write(content)
            temporary.flush()
        result = transcriber.transcribe(str(path), language='ja', task='transcribe',
                                        vad_filter=True, beam_size=5)
        segments = result[0] if isinstance(result, tuple) else result
        pieces = []
        for segment in segments:
            text = getattr(segment, 'text', '')
            if isinstance(text, str) and text.strip():
                pieces.append(text.strip())
        transcript = ''.join(pieces).strip()
        if not transcript:
            raise ValueError('Không nhận ra lời nói trong file audio.')
        return transcript
    finally:
        path.unlink(missing_ok=True)
