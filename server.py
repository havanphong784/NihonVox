"""Local Japanese conversation practice. Run with scripts/run.sh."""

import re
import unicodedata

RULES = {
    'お茶': 'ホットとアイス、どちらにしますか？',
    'おちゃ': 'ホットとアイス、どちらにしますか？',
    'コーヒー': 'ホットとアイス、どちらにしますか？',
    'コーヒーをください': 'ホットとアイス、どちらにしますか？',
    'アイス': 'かしこまりました。',
    'アイスで': 'かしこまりました。',
}
JAPANESE = re.compile(r'[぀-ヿ㐀-鿿]')


def match_rule(text: str) -> str | None:
    normalized = unicodedata.normalize('NFKC', text).strip()
    return RULES.get(re.sub(r'[。！？?!\s]+$', '', normalized))


def first_japanese_sentence(text: str) -> str:
    """Keep a Japanese sentence, never an arbitrary character-length slice."""
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL | re.IGNORECASE)
    # Do not accidentally speak an unfinished reasoning block.
    text = re.sub(r'<think>.*$', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'^\s*```[^\n]*\n?|```\s*$', '', text.strip())
    # Ignore standalone English preambles and Markdown fences.
    lines = text.strip().splitlines()
    start = next((i for i, line in enumerate(lines) if JAPANESE.search(line)), None)
    if start is None:
        raise ValueError('Ollama trả lời rỗng hoặc không có câu tiếng Nhật.')
    text = '\n'.join(lines[start:]).strip()
    for part in re.split(r'(?<=[。！？?!])', text):
        candidate = part.strip()
        if candidate and JAPANESE.search(candidate):
            return candidate
    raise ValueError('Ollama trả lời rỗng hoặc không có câu tiếng Nhật.')


import asyncio
import io
import logging
import os
import time
import uuid
import wave
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated

import httpx
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, StrictBool, StringConstraints

from speech import load_transcriber, transcribe_japanese
from translation import GoogleTranslator
from tutor import (LESSON_PRESETS, LearningFeedback, LearningPreferences, LessonPreset,
                   TUTOR_FORMAT, TutorReply, build_tutor_prompt, get_lesson_preset,
                   parse_tutor_reply)

BASE_DIR = Path(__file__).resolve().parent
logger = logging.getLogger('japanese-assistant')
PRACTICE_ID = re.compile(r'practice-[0-9a-f]{32}')
PRACTICE_EXPIRED = 'Buổi luyện đã kết thúc. Hãy bấm Bắt đầu luyện để mở buổi mới.'
AUDIO_FILENAME = re.compile(r'^[a-f0-9]{32}\.wav$')
SYSTEM_PROMPT = (
    'あなたは日本語会話の練習相手です。自然でやさしい日本語だけで、'
    '短い一文で返答してください。説明、翻訳、箇条書き、思考過程は不要です。'
    '相手がベトナム語で話しても、日本語で会話を続けてください。'
)


@dataclass(frozen=True)
class Settings:
    ollama_url: str = 'http://127.0.0.1:11434'
    ollama_model: str = 'japanese-tutor'
    voicevox_url: str = 'http://127.0.0.1:50021'
    speaker_id: int = 1
    audio_dir: Path = BASE_DIR / 'runtime' / 'audio'
    ollama_timeout: float = 90.0
    voicevox_timeout: float = 20.0
    health_timeout: float = 3.0
    max_turns: int = 10
    max_sessions: int = 128
    session_ttl: float = 21600.0
    max_audio_files: int = 200
    audio_ttl: float = 86400.0
    whisper_model: str = 'small'
    whisper_device: str = 'cpu'
    whisper_compute_type: str = 'int8'
    whisper_download_root: Path = BASE_DIR / 'runtime' / 'whisper'
    max_recording_bytes: int = 10 * 1024 * 1024
    transcription_timeout: float = 120.0
    translation_enabled: bool = True

    @classmethod
    def from_env(cls):
        return cls(
            ollama_url=os.getenv('OLLAMA_URL', cls.ollama_url).rstrip('/'),
            ollama_model=os.getenv('OLLAMA_MODEL', cls.ollama_model),
            voicevox_url=os.getenv('VOICEVOX_URL', cls.voicevox_url).rstrip('/'),
            speaker_id=int(os.getenv('VOICEVOX_SPEAKER_ID', '1')),
            audio_dir=Path(os.getenv('AUDIO_DIR', str(cls.audio_dir))).expanduser().resolve(),
            ollama_timeout=float(os.getenv('OLLAMA_TIMEOUT', '90')),
            voicevox_timeout=float(os.getenv('VOICEVOX_TIMEOUT', '20')),
            whisper_model=os.getenv('WHISPER_MODEL', cls.whisper_model),
            whisper_device=os.getenv('WHISPER_DEVICE', cls.whisper_device),
            whisper_compute_type=os.getenv('WHISPER_COMPUTE_TYPE', cls.whisper_compute_type),
            whisper_download_root=Path(os.getenv('WHISPER_DOWNLOAD_ROOT', str(cls.whisper_download_root))).expanduser().resolve(),
            max_recording_bytes=int(os.getenv('MAX_RECORDING_BYTES', str(cls.max_recording_bytes))),
            transcription_timeout=float(os.getenv('TRANSCRIPTION_TIMEOUT', str(cls.transcription_timeout))),
            translation_enabled=os.getenv('TRANSLATION_ENABLED', '1').strip().lower() not in {'0', 'false', 'no', 'off'},
        )


SessionId = Annotated[str, StringConstraints(strict=True, pattern=r'^[A-Za-z0-9_-]{1,64}$')]


class ChatInput(BaseModel):
    text: Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=2000)]
    session_id: SessionId = 'default'
    translate: StrictBool | None = None


class PracticeSessionInput(LearningPreferences):
    lesson_id: str | None = None
    translate: StrictBool | None = None


class PracticeSentence(BaseModel):
    japanese: str
    vietnamese: str


class PracticeProgress(BaseModel):
    lesson_id: str
    completed_turns: int
    total_turns: int = 5
    completed: bool
    practice_sentence: PracticeSentence | None = None


class ChatOutput(BaseModel):
    reply: str
    audio_url: str | None
    source: str
    session_id: str
    error_audio: str | None = None
    learning: LearningFeedback | None = None
    translation: str | None = None
    error_translation: str | None = None
    progress: PracticeProgress | None = None


class VoiceChatOutput(ChatOutput):
    transcript: str


@dataclass
class Session:
    history: list[dict[str, str]] = field(default_factory=list)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    last_used: float = field(default_factory=time.monotonic)
    users: int = 0
    preferences: LearningPreferences | None = None
    opener: str | None = None
    lesson_id: str | None = None
    completed_turns: int = 0
    translate: bool | None = None


def prune_audio(settings: Settings):
    """Only touch our UUID-named regular files in the configured audio directory."""
    files = []
    now = time.time()
    for path in settings.audio_dir.glob('*.wav'):
        if not AUDIO_FILENAME.fullmatch(path.name) or path.is_symlink():
            continue
        try:
            modified = path.stat().st_mtime
            if now - modified > settings.audio_ttl:
                path.unlink(missing_ok=True)
            elif path.is_file():
                files.append((modified, path))
        except FileNotFoundError:
            continue
    files.sort(key=lambda item: item[0], reverse=True)
    for _, path in files[settings.max_audio_files:]:
        path.unlink(missing_ok=True)


def save_audio(settings: Settings, content: bytes) -> str:
    if len(content) > 16 * 1024 * 1024:
        raise ValueError('Audio quá lớn.')
    # A 200 response containing HTML/JSON is not a playable WAV.
    with wave.open(io.BytesIO(content), 'rb') as audio:
        if audio.getnframes() < 1 or not audio.readframes(1):
            raise ValueError('Audio rỗng.')
    filename = f'{uuid.uuid4().hex}.wav'
    path = settings.audio_dir / filename
    with path.open('xb') as output:
        output.write(content)
    prune_audio(settings)
    return f'/audio/{filename}'


async def ollama_reply(client: httpx.AsyncClient, settings: Settings, history, text: str) -> str:
    return await request_ollama_reply(client, settings, history, text)


async def request_ollama_reply(client: httpx.AsyncClient, settings: Settings, history, text: str,
                               *, preferences: LearningPreferences | None = None,
                               opening: bool = False, lesson: LessonPreset | None = None) -> str | TutorReply:
    prompt = build_tutor_prompt(preferences, opening=opening, lesson=lesson) if preferences else SYSTEM_PROMPT
    payload = {'model': settings.ollama_model, 'think': False, 'stream': False,
               'messages': [{'role': 'system', 'content': prompt}, *history,
                            {'role': 'user', 'content': text}]}
    if preferences:
        payload['format'] = TUTOR_FORMAT
        # The local tutor Modelfile stops at punctuation and caps output at 32 tokens.
        payload['options'] = {'stop': [], 'num_predict': 768, 'num_ctx': 4096}
    try:
        response = await client.post(
            f'{settings.ollama_url}/api/chat',
            json=payload,
            timeout=settings.ollama_timeout,
        )
        if response.status_code == 404:
            raise HTTPException(503, f'Không tìm thấy model {settings.ollama_model} trong Ollama.')
        response.raise_for_status()
        data = response.json()
        content = data.get('message', {}).get('content')
        if not isinstance(content, str):
            raise ValueError('Ollama trả về dữ liệu không hợp lệ.')
        if preferences:
            return parse_tutor_reply(content, preferences, opening=opening)
        reply = first_japanese_sentence(content)
        if len(reply) > 2000:
            raise ValueError('Câu trả lời quá dài; hãy thử lại với câu ngắn hơn.')
        return reply
    except httpx.TimeoutException as exc:
        raise HTTPException(504, 'Ollama phản hồi quá lâu. Vui lòng thử lại.') from exc
    except httpx.ConnectError as exc:
        raise HTTPException(503, 'Ollama đang offline. Hãy khởi động Ollama rồi thử lại.') from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(502, 'Ollama báo lỗi khi tạo câu trả lời.') from exc
    except httpx.RequestError as exc:
        raise HTTPException(503, 'Không kết nối được Ollama. Vui lòng kiểm tra dịch vụ.') from exc
    except (ValueError, TypeError, AttributeError) as exc:
        raise HTTPException(502, 'Ollama trả lời rỗng hoặc không có câu tiếng Nhật hợp lệ.') from exc


async def synthesize(client: httpx.AsyncClient, settings: Settings, reply: str) -> tuple[str | None, str | None]:
    try:
        params = {'speaker': settings.speaker_id, 'text': reply}
        query = await client.get(f'{settings.voicevox_url}/audio_query', params=params,
                                 timeout=settings.voicevox_timeout)
        if query.status_code == 405:
            # Standard VOICEVOX uses POST. Also accept GET-compatible installations.
            query = await client.post(f'{settings.voicevox_url}/audio_query', params=params,
                                      timeout=settings.voicevox_timeout)
        query.raise_for_status()
        data = query.json()
        if not isinstance(data, dict):
            raise ValueError('Audio query không hợp lệ.')
        audio = await client.post(f'{settings.voicevox_url}/synthesis',
                                  params={'speaker': settings.speaker_id}, json=data,
                                  timeout=settings.voicevox_timeout)
        audio.raise_for_status()
        return await asyncio.to_thread(save_audio, settings, audio.content), None
    except httpx.TimeoutException:
        return None, 'VOICEVOX phản hồi quá lâu. Bạn vẫn có thể luyện bằng văn bản.'
    except httpx.ConnectError:
        return None, 'VOICEVOX đang offline. Câu trả lời vẫn hiển thị bằng văn bản.'
    except (httpx.HTTPError, ValueError, TypeError, OSError, EOFError, wave.Error):
        logger.warning('VOICEVOX không tạo được WAV hợp lệ.')
        return None, 'Không tạo được âm thanh từ VOICEVOX. Hãy kiểm tra dịch vụ.'


class VoiceUploadLimitMiddleware:
    """Reject oversized multipart requests before Starlette spools uploaded files."""

    def __init__(self, app, max_request_bytes: int):
        self.app = app
        self.max_request_bytes = max_request_bytes

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope.get('path') != '/voice-chat' or scope.get('method') != 'POST':
            await self.app(scope, receive, send)
            return
        headers = {key.lower(): value for key, value in scope.get('headers', [])}
        raw_length = headers.get(b'content-length')
        if raw_length:
            try:
                if int(raw_length) > self.max_request_bytes:
                    await self._reject(send)
                    return
            except ValueError:
                await self._reject(send, 'Content-Length không hợp lệ.')
                return
        messages = []
        size = 0
        while True:
            message = await receive()
            messages.append(message)
            if message['type'] == 'http.request':
                size += len(message.get('body', b''))
                if size > self.max_request_bytes:
                    await self._reject(send)
                    return
                if not message.get('more_body', False):
                    break
            elif message['type'] == 'http.disconnect':
                return

        async def replay_receive():
            if messages:
                return messages.pop(0)
            return await receive()

        await self.app(scope, replay_receive, send)

    @staticmethod
    async def _reject(send, detail='File audio quá lớn; giới hạn là 10 MiB.'):
        body = __import__('json').dumps({'detail': detail}, ensure_ascii=False).encode('utf-8')
        await send({'type': 'http.response.start', 'status': 422, 'headers': [
            (b'content-type', b'application/json; charset=utf-8'),
            (b'content-length', str(len(body)).encode('ascii')),
            (b'cache-control', b'no-store'),
            (b'x-content-type-options', b'nosniff'),
            (b'content-security-policy', b"default-src 'self'; object-src 'none'; frame-ancestors 'none'"),
        ]})
        await send({'type': 'http.response.body', 'body': body})


_AUTO_TRANSCRIBER = object()


def create_app(settings: Settings | None = None, *, transport=None, transcriber=_AUTO_TRANSCRIBER) -> FastAPI:
    config = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(application):
        config.audio_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        prune_audio(config)
        async with httpx.AsyncClient(transport=transport, trust_env=False,
                                     limits=httpx.Limits(max_connections=20)) as client:
            application.state.http = client
            application.state.translator = GoogleTranslator(client, enabled=config.translation_enabled)
            application.state.sessions = {}
            application.state.audio_lock = asyncio.Lock()
            application.state.speech_lock = asyncio.Lock()
            application.state.transcriber = None if transcriber is _AUTO_TRANSCRIBER else transcriber
            application.state.speech_error = None
            if transcriber is _AUTO_TRANSCRIBER:
                try:
                    application.state.transcriber = await asyncio.to_thread(
                        load_transcriber, config.whisper_model, config.whisper_device,
                        config.whisper_compute_type, config.whisper_download_root)
                except Exception as exc:
                    application.state.speech_error = str(exc)
                    logger.warning('Không tải được model speech local; text chat vẫn hoạt động.')
            yield

    app = FastAPI(title='Luyện hội thoại tiếng Nhật', lifespan=lifespan)
    app.add_middleware(VoiceUploadLimitMiddleware, max_request_bytes=config.max_recording_bytes + 64 * 1024)
    app.state.settings = config
    app.mount('/static', StaticFiles(directory=BASE_DIR / 'static'), name='static')

    @app.exception_handler(RequestValidationError)
    async def invalid_input(request, exc):
        if request.url.path == '/practice-sessions':
            return JSONResponse(status_code=422, content={'detail': 'Chọn trình độ, loại chữ và chủ đề hợp lệ.'})
        return JSONResponse(status_code=422, content={
            'detail': 'Nhập từ 1–2000 ký tự; session_id chỉ gồm chữ, số, dấu gạch ngang hoặc gạch dưới (tối đa 64 ký tự).'
        })

    @app.exception_handler(Exception)
    async def internal_error(request, exc):
        logger.error('Lỗi nội bộ khi xử lý yêu cầu.', exc_info=exc)
        return JSONResponse(status_code=500, content={'detail': 'Server gặp lỗi. Vui lòng thử lại.'})

    @app.middleware('http')
    async def security_headers(request: Request, call_next):
        # No CORS and no cross-origin state mutations; intended for loopback use only.
        origin = request.headers.get('origin')
        if request.method in {'POST', 'DELETE'} and origin and origin != str(request.base_url).rstrip('/'):
            return JSONResponse(status_code=403, content={'detail': 'Không chấp nhận yêu cầu từ trang khác.'})
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "media-src 'self'; connect-src 'self'; img-src 'self' data:; "
            "object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
        )
        if request.url.path in {'/', '/health', '/lessons', '/practice-sessions', '/chat', '/transcribe', '/voice-chat'} or request.url.path.startswith('/sessions'):
            response.headers['Cache-Control'] = 'no-store'
        return response

    @app.get('/')
    async def index():
        return FileResponse(BASE_DIR / 'static' / 'index.html', media_type='text/html')

    @app.get('/health')
    async def health():
        async def check_ollama():
            try:
                response = await app.state.http.get(f'{config.ollama_url}/api/tags', timeout=config.health_timeout)
                response.raise_for_status()
                data = response.json()
                models = data['models']
                if not isinstance(models, list):
                    return False, False
                accepted = {config.ollama_model}
                if ':' not in config.ollama_model:
                    accepted.add(config.ollama_model + ':latest')
                found = any(isinstance(model, dict) and
                            (model.get('name') in accepted or model.get('model') in accepted) for model in models)
                return True, found
            except (httpx.HTTPError, ValueError, TypeError, KeyError):
                return False, False

        async def check_voicevox():
            try:
                response = await app.state.http.get(f'{config.voicevox_url}/version', timeout=config.health_timeout)
                response.raise_for_status()
                return isinstance(response.json(), str)
            except (httpx.HTTPError, ValueError):
                return False

        (ollama, model), voicevox = await asyncio.gather(check_ollama(), check_voicevox())
        speech_model = app.state.transcriber is not None
        return {'status': 'ok' if ollama and model and voicevox and speech_model else 'degraded',
                'ollama': ollama, 'model': model, 'voicevox': voicevox,
                'speech_model': speech_model, 'translation_enabled': config.translation_enabled}

    def prune_sessions():
        sessions = app.state.sessions
        now = time.monotonic()
        for key, value in list(sessions.items()):
            if value.users == 0 and now - value.last_used > config.session_ttl:
                del sessions[key]

    def find_session(session_id: str) -> Session | None:
        prune_sessions()
        session = app.state.sessions.get(session_id)
        if PRACTICE_ID.fullmatch(session_id) and (session is None or session.opener is None):
            raise HTTPException(410, PRACTICE_EXPIRED)
        return session

    def reserve_session(session_id: str, preferences: LearningPreferences | None = None,
                       lesson_id: str | None = None, translate: bool | None = None) -> Session:
        sessions = app.state.sessions
        if len(sessions) >= config.max_sessions:
            raise HTTPException(503, 'Có quá nhiều phiên hội thoại. Hãy xóa phiên cũ hoặc thử lại sau.')
        session = sessions[session_id] = Session(preferences=preferences, lesson_id=lesson_id, translate=translate)
        return session

    def lesson_progress(session: Session) -> PracticeProgress | None:
        if session.lesson_id is None:
            return None
        lesson = get_lesson_preset(session.lesson_id)
        return PracticeProgress(
            lesson_id=lesson.id,
            completed_turns=session.completed_turns,
            total_turns=5,
            completed=session.completed_turns >= 5,
            practice_sentence=PracticeSentence(
                japanese=lesson.practice_sentence_japanese,
                vietnamese=lesson.practice_sentence_vietnamese,
            ) if session.completed_turns >= 5 else None,
        )

    async def play_reply(session_id: str, reply: str, source: str,
                         learning: LearningFeedback | None = None,
                         translate: bool | None = None) -> ChatOutput:
        async def make_audio():
            async with app.state.audio_lock:
                return await synthesize(app.state.http, config, reply)

        async def make_translation():
            enabled = config.translation_enabled and (translate is not False)
            if not enabled:
                return None, None
            return await app.state.translator.translate(reply)

        (audio_url, error_audio), (translation, error_translation) = await asyncio.gather(
            make_audio(), make_translation())
        result = ChatOutput(reply=reply, audio_url=audio_url, source=source,
                            session_id=session_id, error_audio=error_audio,
                            translation=translation, error_translation=error_translation)
        if learning is not None:
            result.learning = learning
        return result

    @app.get('/lessons')
    async def lessons():
        return {'lessons': [lesson.model_dump(exclude={'context', 'practice_sentence_japanese',
                                                        'practice_sentence_vietnamese'})
                            for lesson in LESSON_PRESETS]}

    @app.post('/practice-sessions', response_model=ChatOutput, status_code=201, response_model_exclude_unset=True)
    async def start_practice(request: PracticeSessionInput) -> ChatOutput:
        prune_sessions()
        lesson = None
        if request.lesson_id is not None:
            try:
                lesson = get_lesson_preset(request.lesson_id)
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from exc
            preferences = LearningPreferences(level=lesson.level, script=lesson.script, topic=lesson.topic)
        else:
            preferences = LearningPreferences(level=request.level, script=request.script, topic=request.topic)
        session_id = f'practice-{uuid.uuid4().hex}'
        session = reserve_session(session_id, preferences, request.lesson_id, request.translate)
        session.users = 1
        try:
            async with session.lock:
                turn = await request_ollama_reply(app.state.http, config, [], '会話練習を始めてください。',
                                                  preferences=preferences, opening=True, lesson=lesson)
                result = await play_reply(session_id, turn.reply, 'ollama', turn.learning, request.translate)
                session.opener = turn.reply
                progress = lesson_progress(session)
                if progress is not None:
                    result.progress = progress
                return result
        finally:
            session.users = 0
            session.last_used = time.monotonic()
            if session.opener is None:
                app.state.sessions.pop(session_id, None)

    async def process_text_turn(session_id: str, text: str, translate: bool | None = None) -> ChatOutput:
        session = find_session(session_id) or reserve_session(session_id)
        session.users += 1
        try:
            async with session.lock:
                if session.preferences is not None:
                    if app.state.sessions.get(session_id) is not session:
                        raise HTTPException(410, PRACTICE_EXPIRED)
                    if session.lesson_id is not None and session.completed_turns >= 5:
                        raise HTTPException(409, 'Buổi luyện đã hoàn thành. Hãy bấm Luyện lại bài hoặc bắt đầu bài mới.')
                    lesson = get_lesson_preset(session.lesson_id) if session.lesson_id else None
                    history = [{'role': 'assistant', 'content': session.opener}, *session.history]
                    turn = await request_ollama_reply(app.state.http, config, history, text,
                                                      preferences=session.preferences, lesson=lesson)
                    reply, learning, source = turn.reply, turn.learning, 'ollama'
                    effective_translate = session.translate if translate is None else translate
                else:
                    reply = match_rule(text)
                    source = 'rule' if reply is not None else 'ollama'
                    if reply is None:
                        reply = await ollama_reply(app.state.http, config, session.history, text)
                    learning = None
                    effective_translate = translate
                session.history.extend([{'role': 'user', 'content': text},
                                        {'role': 'assistant', 'content': reply}])
                del session.history[:-config.max_turns * 2]
                if session.lesson_id is not None:
                    session.completed_turns += 1
                result = await play_reply(session_id, reply, source, learning, effective_translate)
                progress = lesson_progress(session)
                if progress is not None:
                    result.progress = progress
                return result
        finally:
            session.users -= 1
            session.last_used = time.monotonic()

    app.state.process_text_turn = process_text_turn

    @app.post('/chat', response_model=ChatOutput, response_model_exclude_unset=True)
    async def chat(message: ChatInput):
        return await process_text_turn(message.session_id, message.text, message.translate)

    async def transcribe_upload(audio: UploadFile) -> str:
        if app.state.transcriber is None:
            raise HTTPException(503, 'Nhận dạng giọng nói local chưa sẵn sàng. Bạn có thể nhập văn bản.')
        allowed_types = {
            'audio/webm': '.webm', 'audio/ogg': '.ogg', 'audio/wav': '.wav',
            'audio/x-wav': '.wav', 'audio/mp4': '.mp4', 'audio/mpeg': '.mp4',
        }
        content_type = (audio.content_type or '').split(';', 1)[0].lower()
        suffix = allowed_types.get(content_type)
        if suffix is None:
            name = (audio.filename or '').lower()
            suffix = next((candidate for candidate in ('.webm', '.ogg', '.wav', '.mp4') if name.endswith(candidate)), None)
        if suffix is None:
            raise HTTPException(422, 'Định dạng audio không được hỗ trợ.')
        content = await audio.read(config.max_recording_bytes + 1)
        if not content:
            raise HTTPException(422, 'File audio rỗng.')
        if len(content) > config.max_recording_bytes:
            raise HTTPException(422, 'File audio quá lớn; giới hạn là 10 MiB.')

        async def run_transcription():
            async with app.state.speech_lock:
                return await asyncio.to_thread(
                    transcribe_japanese, app.state.transcriber, io.BytesIO(content), suffix,
                    config.audio_dir.parent / 'transient')

        task = asyncio.create_task(run_transcription())
        try:
            return await asyncio.wait_for(asyncio.shield(task), timeout=config.transcription_timeout)
        except asyncio.TimeoutError as exc:
            def consume_finished(done):
                try:
                    done.result()
                except Exception:
                    pass
            task.add_done_callback(consume_finished)
            raise HTTPException(504, 'Nhận dạng giọng nói quá lâu. Vui lòng thử lại.') from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        except Exception as exc:
            logger.warning('Whisper không nhận dạng được audio.')
            raise HTTPException(502, 'Không nhận dạng được giọng nói. Vui lòng thử lại.') from exc

    @app.post('/transcribe')
    async def transcribe(audio: UploadFile = File(...)):
        try:
            return {'transcript': await transcribe_upload(audio)}
        finally:
            await audio.close()

    @app.post('/voice-chat', response_model=VoiceChatOutput, response_model_exclude_unset=True)
    async def voice_chat(audio: UploadFile = File(...), session_id: SessionId = Form('default'),
                         translate: bool | None = Form(None)):
        if PRACTICE_ID.fullmatch(session_id):
            find_session(session_id)
        try:
            transcript = await transcribe_upload(audio)
            result = await process_text_turn(session_id, transcript, translate)
            return VoiceChatOutput(transcript=transcript, **result.model_dump(exclude_unset=True))
        finally:
            await audio.close()

    @app.delete('/sessions/{session_id}')
    async def clear_session(session_id: SessionId):
        session = app.state.sessions.get(session_id)
        if session is not None:
            async with session.lock:
                session.history.clear()
                if app.state.sessions.get(session_id) is session and (session.preferences is not None or session.users == 0):
                    app.state.sessions.pop(session_id, None)
        return {'status': 'cleared', 'session_id': session_id}

    @app.get('/audio/{filename}')
    async def audio(filename: str):
        if not AUDIO_FILENAME.fullmatch(filename):
            raise HTTPException(404, 'Không tìm thấy âm thanh.')
        path = config.audio_dir / filename
        if path.is_symlink() or not path.is_file() or path.resolve().parent != config.audio_dir.resolve():
            raise HTTPException(404, 'Không tìm thấy âm thanh.')
        return FileResponse(path, media_type='audio/wav', headers={'Cache-Control': 'private, max-age=3600'})

    return app


app = create_app()
