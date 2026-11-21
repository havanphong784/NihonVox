import io
import json
import re
import wave

import httpx
import pytest
from fastapi.testclient import TestClient


def wav_bytes():
    output = io.BytesIO()
    with wave.open(output, 'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(24000)
        audio.writeframes(b'\0\0' * 2400)
    return output.getvalue()


@pytest.fixture
def system(tmp_path):
    from server import Settings, create_app
    state = {'requests': [], 'ollama': 'ok', 'voicevox': 'ok',
             'model': True, 'reply': 'そうですね。散歩しましょう。',
             'query_method': 'GET', 'translation': 'ok'}

    def upstream(request):
        state['requests'].append(request)
        path = request.url.path
        if request.url.host == 'translate.googleapis.com':
            mode = state['translation']
            if mode == 'offline':
                raise httpx.ConnectError('offline', request=request)
            if mode == 'timeout':
                raise httpx.ReadTimeout('timeout', request=request)
            if mode == 'blocked':
                return httpx.Response(429)
            if mode == 'malformed':
                return httpx.Response(200, text='<html>blocked</html>')
            return httpx.Response(200, json=[[['Bản dịch tiếng Việt.', request.url.params['q']]], None, 'ja'])
        if request.url.host == 'ollama.test':
            mode = state['ollama']
            if mode == 'offline':
                raise httpx.ConnectError('offline', request=request)
            if mode == 'timeout':
                raise httpx.ReadTimeout('timeout', request=request)
            if mode == 'bad_json':
                return httpx.Response(200, text='not json')
            if path == '/api/tags':
                return httpx.Response(200, json={'models': [{'name': 'japanese-tutor:latest'}] if state['model'] else []})
            if not state['model']:
                return httpx.Response(404, json={'error': 'model not found'})
            return httpx.Response(200, json={'message': {'role': 'assistant', 'content': state['reply']}})
        mode = state['voicevox']
        if mode == 'offline':
            raise httpx.ConnectError('offline', request=request)
        if mode == 'timeout':
            raise httpx.ReadTimeout('timeout', request=request)
        if path == '/version':
            return httpx.Response(200, json='test-version')
        if path == '/audio_query':
            if request.method != state['query_method']:
                return httpx.Response(405)
            if mode == 'bad_json':
                return httpx.Response(200, text='not json')
            return httpx.Response(200, json={'accent_phrases': [], 'speedScale': 1.0})
        if path == '/synthesis':
            content = b'not wav' if mode == 'bad_wav' else wav_bytes()
            return httpx.Response(200, content=content, headers={'content-type': 'audio/wav'})
        raise AssertionError(f'Unexpected request {request.method} {request.url}')

    settings = Settings(ollama_url='http://ollama.test', voicevox_url='http://voicevox.test',
                        audio_dir=tmp_path / 'audio', max_turns=3, max_audio_files=4,
                        max_sessions=3, transcription_timeout=2.0)
    app = create_app(settings, transport=httpx.MockTransport(upstream), transcriber=FakeSpeechTranscriber())
    with TestClient(app) as client:
        yield client, state, settings


def chat(client, text='お茶', session='default'):
    return client.post('/chat', json={'text': text, 'session_id': session})


def test_root_serves_web_app(system):
    client, _, _ = system
    response = client.get('/')
    assert response.status_code == 200
    assert 'Luyện hội thoại tiếng Nhật' in response.text
    assert client.get('/static/app.js').status_code == 200
    assert client.get('/static/style.css').status_code == 200


def test_health_reports_all_dependencies(system):
    client, _, _ = system
    assert client.get('/health').json() == {'status': 'ok', 'ollama': True, 'model': True, 'voicevox': True, 'speech_model': True, 'translation_enabled': True}


@pytest.mark.parametrize(('change', 'expected'), [
    ({'ollama': 'offline'}, {'status': 'degraded', 'ollama': False, 'model': False, 'voicevox': True, 'speech_model': True, 'translation_enabled': True}),
    ({'voicevox': 'offline'}, {'status': 'degraded', 'ollama': True, 'model': True, 'voicevox': False, 'speech_model': True, 'translation_enabled': True}),
    ({'model': False}, {'status': 'degraded', 'ollama': True, 'model': False, 'voicevox': True, 'speech_model': True, 'translation_enabled': True}),
    ({'ollama': 'bad_json'}, {'status': 'degraded', 'ollama': False, 'model': False, 'voicevox': True, 'speech_model': True, 'translation_enabled': True}),
])
def test_health_degrades_independently(system, change, expected):
    client, state, _ = system
    state.update(change)
    assert client.get('/health').json() == expected


def test_rule_bypasses_ollama_and_serves_generated_wav(system):
    client, state, _ = system
    response = chat(client)
    assert response.status_code == 200
    result = response.json()
    assert result['reply'] == 'ホットとアイス、どちらにしますか？'
    assert result['source'] == 'rule'
    assert result['session_id'] == 'default'
    assert re.fullmatch(r'/audio/[a-f0-9]{32}\.wav', result['audio_url'])
    assert all(r.url.host != 'ollama.test' for r in state['requests'])
    audio = client.get(result['audio_url'])
    assert audio.status_code == 200
    assert audio.content == wav_bytes()
    query = next(r for r in state['requests'] if r.url.path == '/audio_query')
    assert query.url.params['speaker'] == '1'
    assert query.url.params['text'] == result['reply']
    synth = next(r for r in state['requests'] if r.url.path == '/synthesis')
    assert synth.method == 'POST'
    assert json.loads(synth.content)['speedScale'] == 1.0


def test_voicevox_standard_post_query_is_supported(system):
    client, state, _ = system
    state['query_method'] = 'POST'
    assert chat(client).json()['audio_url']
    assert [r.method for r in state['requests'] if r.url.path == '/audio_query'] == ['GET', 'POST']


@pytest.mark.parametrize('mode', ['offline', 'timeout', 'bad_json', 'bad_wav'])
def test_audio_failure_preserves_text(system, mode):
    client, state, _ = system
    state['voicevox'] = mode
    response = chat(client)
    assert response.status_code == 200
    assert response.json()['reply'] == 'ホットとアイス、どちらにしますか？'
    assert response.json()['audio_url'] is None
    assert response.json()['error_audio']


def test_ollama_payload_and_history_includes_rules(system):
    client, state, _ = system
    chat(client)
    response = chat(client, '今日はいい天気ですね。')
    assert response.status_code == 200
    assert response.json()['source'] == 'ollama'
    assert response.json()['reply'] == 'そうですね。'
    request = next(r for r in state['requests'] if r.url.path == '/api/chat')
    payload = json.loads(request.content)
    assert payload['model'] == 'japanese-tutor'
    assert payload['think'] is False
    assert payload['stream'] is False
    assert payload['messages'][0]['role'] == 'system'
    assert payload['messages'][1:] == [
        {'role': 'user', 'content': 'お茶'},
        {'role': 'assistant', 'content': 'ホットとアイス、どちらにしますか？'},
        {'role': 'user', 'content': '今日はいい天気ですね。'},
    ]


def test_sessions_are_isolated_and_can_be_cleared(system):
    client, state, _ = system
    chat(client, 'お茶', 'a')
    chat(client, 'こんにちは', 'b')
    requests = [r for r in state['requests'] if r.url.path == '/api/chat']
    assert len(json.loads(requests[-1].content)['messages']) == 2
    assert client.delete('/sessions/a').status_code == 200
    chat(client, 'こんにちは', 'a')
    requests = [r for r in state['requests'] if r.url.path == '/api/chat']
    assert len(json.loads(requests[-1].content)['messages']) == 2
    assert client.delete('/sessions/default').status_code == 200


def test_history_is_bounded_to_recent_complete_turns(system):
    client, state, _ = system
    for i in range(6):
        assert chat(client, f'質問{i}').status_code == 200
    requests = [json.loads(r.content) for r in state['requests'] if r.url.path == '/api/chat']
    messages = requests[-1]['messages']
    assert len(messages) == 8  # system + 3 retained pairs + current user
    assert messages[1]['content'] == '質問2'
    assert messages[-1]['content'] == '質問5'


@pytest.mark.parametrize(('mode', 'status'), [('offline', 503), ('timeout', 504), ('bad_json', 502)])
def test_ollama_errors_are_explicit_and_do_not_synthesize(system, mode, status):
    client, state, _ = system
    state['ollama'] = mode
    response = chat(client, 'こんにちは')
    assert response.status_code == status
    assert isinstance(response.json()['detail'], str)
    assert not any(r.url.path == '/audio_query' for r in state['requests'])


@pytest.mark.parametrize('reply', ['', ' \n ', 'Hello!', '<think>考え中</think>'])
def test_unusable_reply_does_not_call_voicevox(system, reply):
    client, state, _ = system
    state['reply'] = reply
    assert chat(client, 'こんにちは').status_code == 502
    assert not any(r.url.path == '/audio_query' for r in state['requests'])


def test_missing_model_has_clear_error(system):
    client, state, _ = system
    state['model'] = False
    response = chat(client, 'こんにちは')
    assert response.status_code == 503
    assert 'model' in response.json()['detail'].lower()


@pytest.mark.parametrize('payload', [
    {'text': ''}, {'text': '  \n '}, {'text': 'a' * 2001},
    {'text': 123}, {'text': 'こんにちは', 'session_id': '../etc'},
    {'text': 'こんにちは', 'session_id': ''},
    {'text': 'こんにちは', 'session_id': 'x' * 65}, {},
])
def test_invalid_inputs_do_not_reach_upstreams(system, payload):
    client, state, _ = system
    response = client.post('/chat', json=payload)
    assert response.status_code == 422
    assert isinstance(response.json()['detail'], str)
    assert not state['requests']


@pytest.mark.parametrize('path', [
    '/audio/not-a-uuid.wav', '/audio/requirements.txt',
    '/audio/%2e%2e%2fserver.py', '/audio/' + '0' * 32 + '.wav',
])
def test_audio_rejects_non_generated_paths(system, path):
    client, _, _ = system
    assert client.get(path).status_code == 404


def test_audio_does_not_serve_symlinks(system, tmp_path):
    client, _, settings = system
    secret = tmp_path / 'secret.wav'
    secret.write_bytes(wav_bytes())
    filename = 'a' * 32 + '.wav'
    (settings.audio_dir / filename).symlink_to(secret)
    assert client.get('/audio/' + filename).status_code == 404


def test_audio_files_are_bounded(system):
    client, _, settings = system
    for _ in range(7):
        assert chat(client).status_code == 200
    assert len(list(settings.audio_dir.glob('*.wav'))) <= 4


def test_excess_sessions_have_explicit_capacity_error(system):
    client, _, _ = system
    for session in ['one', 'two', 'three']:
        assert chat(client, session=session).status_code == 200
    response = chat(client, session='four')
    assert response.status_code == 503


def test_server_error_is_json_without_internal_details(system, monkeypatch):
    import server
    client, _, _ = system
    def broken(_):
        raise RuntimeError('private internal path')
    monkeypatch.setattr(server, 'match_rule', broken)
    with TestClient(client.app, raise_server_exceptions=False) as other:
        response = chat(other)
    assert response.status_code == 500
    assert 'private internal path' not in response.text
    assert isinstance(response.json()['detail'], str)


def test_failed_turn_does_not_pollute_history(system):
    client, state, _ = system
    state['ollama'] = 'offline'
    assert chat(client, '失敗した質問').status_code == 503
    state['ollama'] = 'ok'
    assert chat(client, 'こんにちは').status_code == 200
    requests = [r for r in state['requests'] if r.url.path == '/api/chat']
    assert len(json.loads(requests[-1].content)['messages']) == 2


def test_clear_releases_session_capacity(system):
    client, _, _ = system
    for name in ['a', 'b', 'c']:
        assert chat(client, session=name).status_code == 200
    assert client.delete('/sessions/a').status_code == 200
    assert chat(client, session='d').status_code == 200


def test_expired_sessions_are_removed(system):
    client, _, settings = system
    chat(client, session='old')
    client.app.state.sessions['old'].last_used -= settings.session_ttl + 1
    assert chat(client, session='new').status_code == 200
    assert 'old' not in client.app.state.sessions


def test_expired_audio_is_pruned_without_deleting_unrelated_files(system):
    import os
    client, _, settings = system
    stale = settings.audio_dir / ('b' * 32 + '.wav')
    stale.write_bytes(wav_bytes())
    os.utime(stale, (1, 1))
    unrelated = settings.audio_dir / 'keep.txt'
    unrelated.write_text('keep')
    chat(client)
    assert not stale.exists()
    assert unrelated.read_text() == 'keep'


def test_cross_origin_mutations_are_rejected(system):
    client, state, _ = system
    response = client.post('/chat', json={'text': 'お茶'}, headers={'Origin': 'http://another-site.test'})
    assert response.status_code == 403
    assert not state['requests']


def test_voicevox_configuration_comes_from_environment(monkeypatch):
    from server import Settings
    monkeypatch.setenv('VOICEVOX_URL', 'http://localhost:9999/')
    monkeypatch.setenv('VOICEVOX_SPEAKER_ID', '8')
    settings = Settings.from_env()
    assert settings.voicevox_url == 'http://localhost:9999'
    assert settings.speaker_id == 8


def test_reset_waits_for_inflight_turn_and_other_sessions_can_progress(tmp_path):
    import asyncio
    from server import Settings, create_app

    async def scenario():
        entered = asyncio.Event()
        release = asyncio.Event()
        payloads = []

        async def handler(request):
            if request.url.path == '/api/chat':
                payloads.append(json.loads(request.content))
                if len(payloads) == 1:
                    entered.set()
                    await release.wait()
                return httpx.Response(200, json={'message': {'content': 'こんにちは。'}})
            raise httpx.ConnectError('speech offline', request=request)

        settings = Settings(audio_dir=tmp_path / 'audio')
        app = create_app(settings, transport=httpx.MockTransport(handler), transcriber=None)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://testserver') as client:
                first = asyncio.create_task(client.post('/chat', json={'text': 'こんにちは', 'session_id': 'a'}))
                await asyncio.wait_for(entered.wait(), 2)
                reset = asyncio.create_task(client.delete('/sessions/a'))
                other = await asyncio.wait_for(client.post('/chat', json={'text': 'お茶', 'session_id': 'b'}), 2)
                assert other.status_code == 200
                assert not reset.done()
                release.set()
                assert (await first).status_code == 200
                assert (await reset).status_code == 200
                assert (await client.post('/chat', json={'text': '元気ですか', 'session_id': 'a'})).status_code == 200
                assert len(payloads[-1]['messages']) == 2

    asyncio.run(scenario())


def test_chat_exposes_shared_text_turn_pipeline(system):
    client, _, _ = system
    assert callable(client.app.state.process_text_turn)
    response = chat(client, 'お茶', 'shared-pipeline')
    assert response.status_code == 200
    assert response.json()['reply'] == 'ホットとアイス、どちらにしますか？'


class FakeSpeechTranscriber:
    def __init__(self, text='今日はいい天気ですね。', error=None):
        self.text = text
        self.error = error
        self.calls = []

    def transcribe(self, path, **kwargs):
        self.calls.append((path, kwargs))
        if self.error:
            raise self.error
        return iter([type('Segment', (), {'text': self.text})()]), {'language': kwargs['language']}


def voice_chat(client, content=b'RIFFfake-audio', filename='sample.wav', content_type='audio/wav', session='default'):
    return client.post('/voice-chat', data={'session_id': session},
                       files={'audio': (filename, content, content_type)})


def test_voice_chat_returns_transcript_and_reuses_session(system):
    client, state, _ = system
    speech = FakeSpeechTranscriber('今日はいい天気ですね。')
    client.app.state.transcriber = speech
    response = voice_chat(client, session='voice-session')
    assert response.status_code == 200
    result = response.json()
    assert result['transcript'] == '今日はいい天気ですね。'
    assert result['source'] == 'ollama'
    assert result['session_id'] == 'voice-session'
    payload = json.loads(next(r for r in state['requests'] if r.url.path == '/api/chat').content)
    assert payload['think'] is False
    assert payload['messages'][-1] == {'role': 'user', 'content': '今日はいい天気ですね。'}
    assert speech.calls[0][1] == {'language': 'ja', 'task': 'transcribe', 'vad_filter': True, 'beam_size': 5}


def test_voice_health_reports_model_readiness(system):
    client, _, _ = system
    client.app.state.transcriber = FakeSpeechTranscriber()
    assert client.get('/health').json()['speech_model'] is True


def test_unavailable_whisper_preserves_typed_chat(system):
    client, _, _ = system
    client.app.state.transcriber = None
    client.app.state.speech_error = 'Whisper unavailable'
    assert chat(client, 'お茶').status_code == 200
    health = client.get('/health').json()
    assert health['speech_model'] is False


def test_empty_audio_does_not_invoke_transcriber(system):
    client, _, _ = system
    speech = FakeSpeechTranscriber()
    client.app.state.transcriber = speech
    response = voice_chat(client, b'', filename='empty.wav')
    assert response.status_code == 422
    assert speech.calls == []


def test_oversized_audio_is_rejected_before_full_read(system):
    client, _, settings = system
    speech = FakeSpeechTranscriber()
    client.app.state.transcriber = speech
    response = voice_chat(client, b'x' * (settings.max_recording_bytes + 1))
    assert response.status_code == 422
    assert speech.calls == []


def test_unsupported_mime_is_rejected(system):
    client, _, _ = system
    speech = FakeSpeechTranscriber()
    client.app.state.transcriber = speech
    response = voice_chat(client, b'audio', filename='sample.exe', content_type='application/octet-stream')
    assert response.status_code == 422
    assert speech.calls == []


def test_empty_transcription_does_not_call_ollama(system):
    client, state, _ = system
    client.app.state.transcriber = FakeSpeechTranscriber('   ')
    response = voice_chat(client)
    assert response.status_code == 422
    assert not any(r.url.path == '/api/chat' for r in state['requests'])


def test_transcription_failure_does_not_call_ollama_or_voicevox(system):
    client, state, _ = system
    client.app.state.transcriber = FakeSpeechTranscriber(error=RuntimeError('decoder failure'))
    response = voice_chat(client)
    assert response.status_code == 502
    assert not any(r.url.path in {'/api/chat', '/audio_query'} for r in state['requests'])


def test_uploaded_recording_is_not_retained(system):
    client, _, settings = system
    client.app.state.transcriber = FakeSpeechTranscriber()
    assert voice_chat(client).status_code == 200
    assert not list(settings.audio_dir.glob('voice-*'))


def test_transcription_timeout_is_504(system, monkeypatch):
    import server
    client, state, _ = system
    client.app.state.transcriber = FakeSpeechTranscriber()
    monkeypatch.setattr(server, 'transcribe_japanese', lambda *args, **kwargs: __import__('time').sleep(0.2))
    object.__setattr__(client.app.state.settings, 'transcription_timeout', 0.01)
    response = voice_chat(client)
    assert response.status_code == 504
    assert not any(r.url.path in {'/api/chat', '/audio_query'} for r in state['requests'])


def test_chunked_voice_body_is_rejected_before_multipart_parser(system, monkeypatch):
    import asyncio
    from starlette.requests import Request as StarletteRequest

    client, _, _ = system
    parser_calls = []
    original = StarletteRequest._get_form

    async def observed_form(request, *args, **kwargs):
        parser_calls.append(True)
        return await original(request, *args, **kwargs)

    monkeypatch.setattr(StarletteRequest, '_get_form', observed_form)

    class ChunkedUpload(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b'--voice-boundary\r\nContent-Disposition: form-data; name="audio"; filename="clip.wav"\r\nContent-Type: audio/wav\r\n\r\n'
            yield b'x' * (10 * 1024 * 1024 + 64 * 1024 + 1)

        async def aclose(self):
            return None

    async def send():
        transport = httpx.ASGITransport(app=client.app)
        async with httpx.AsyncClient(transport=transport, base_url='http://testserver') as sender:
            return await sender.post('/voice-chat', content=ChunkedUpload(),
                                     headers={'Content-Type': 'multipart/form-data; boundary=voice-boundary'})

    response = asyncio.run(send())
    assert response.status_code == 422
    assert parser_calls == []


def transcribe(client, content=b'RIFFfake-audio', filename='sample.wav', content_type='audio/wav'):
    return client.post('/transcribe', files={'audio': (filename, content, content_type)})


def test_transcribe_returns_only_transcript_without_session_or_upstreams(system):
    client, state, _ = system
    speech = FakeSpeechTranscriber('文字起こしだけです。')
    client.app.state.transcriber = speech
    response = transcribe(client)
    assert response.status_code == 200
    assert response.json() == {'transcript': '文字起こしだけです。'}
    assert client.app.state.sessions == {}
    assert speech.calls
    assert not any(request.url.host in {'ollama.test', 'voicevox.test', 'translate.googleapis.com'}
                   for request in state['requests'])


@pytest.mark.parametrize(('content', 'filename', 'content_type'), [
    (b'', 'empty.wav', 'audio/wav'),
    (b'audio', 'sample.exe', 'application/octet-stream'),
])
def test_transcribe_reuses_upload_validation(system, content, filename, content_type):
    client, _, _ = system
    speech = FakeSpeechTranscriber()
    client.app.state.transcriber = speech
    response = transcribe(client, content, filename, content_type)
    assert response.status_code == 422
    assert speech.calls == []


def test_transcribe_rejects_oversized_upload_before_transcriber(system):
    client, _, settings = system
    speech = FakeSpeechTranscriber()
    client.app.state.transcriber = speech
    response = transcribe(client, b'x' * (settings.max_recording_bytes + 1))
    assert response.status_code == 422
    assert speech.calls == []


def test_transcribe_decoder_failure_does_not_call_upstreams(system):
    client, state, _ = system
    client.app.state.transcriber = FakeSpeechTranscriber(error=RuntimeError('decoder failure'))
    response = transcribe(client)
    assert response.status_code == 502
    assert not any(request.url.host in {'ollama.test', 'voicevox.test', 'translate.googleapis.com'}
                   for request in state['requests'])


def test_transcribe_timeout_is_504(system, monkeypatch):
    import server
    client, state, _ = system
    client.app.state.transcriber = FakeSpeechTranscriber()
    monkeypatch.setattr(server, 'transcribe_japanese', lambda *args, **kwargs: __import__('time').sleep(0.2))
    object.__setattr__(client.app.state.settings, 'transcription_timeout', 0.01)
    response = transcribe(client)
    assert response.status_code == 504
    assert not state['requests']


def test_chat_request_can_disable_translation_without_disabling_server(system):
    client, state, _ = system
    response = client.post('/chat', json={'text': 'お茶', 'translate': False})
    assert response.status_code == 200
    assert response.json()['translation'] is None
    assert response.json()['error_translation'] is None
    assert not any(request.url.host == 'translate.googleapis.com' for request in state['requests'])


def test_chat_request_can_enable_translation_and_sends_only_reply(system):
    client, state, _ = system
    response = client.post('/chat', json={'text': 'PRIVATE LEARNER INPUT', 'translate': True})
    assert response.status_code == 200
    assert response.json()['translation'] == 'Bản dịch tiếng Việt.'
    google = [request for request in state['requests'] if request.url.host == 'translate.googleapis.com']
    assert len(google) == 1
    assert google[0].url.params['q'] == response.json()['reply']


def test_practice_translation_choice_is_used_for_opening_and_followup(system):
    client, state, _ = system
    prepare = json.dumps({'reply': 'こんにちは。', 'correction': None, 'exercise': None}, ensure_ascii=False)
    state['reply'] = prepare
    started = client.post('/practice-sessions', json={'lesson_id': 'order-food', 'translate': False})
    assert started.status_code == 201
    session = started.json()['session_id']
    state['reply'] = json.dumps({'reply': 'はい、どうぞ。', 'correction': None, 'exercise': None}, ensure_ascii=False)
    response = client.post('/chat', json={'text': 'お茶', 'session_id': session})
    assert response.status_code == 200
    assert response.json()['translation'] is None
    assert not any(request.url.host == 'translate.googleapis.com' for request in state['requests'])


def test_server_translation_disabled_overrides_explicit_request(system, monkeypatch):
    client, state, settings = system
    object.__setattr__(settings, 'translation_enabled', False)
    response = client.post('/chat', json={'text': 'お茶', 'translate': True})
    assert response.status_code == 200
    assert response.json()['translation'] is None and response.json()['error_translation'] is None
    assert not any(request.url.host == 'translate.googleapis.com' for request in state['requests'])


def test_health_reports_translation_capability(system):
    client, _, settings = system
    assert client.get('/health').json()['translation_enabled'] is True
    object.__setattr__(settings, 'translation_enabled', False)
    assert client.get('/health').json()['translation_enabled'] is False
