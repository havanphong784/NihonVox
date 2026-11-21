import json
import re

import httpx

import pytest

from test_api import chat, system, voice_chat, wav_bytes

PREFERENCES = {'level': 'N5', 'script': 'katakana', 'topic': 'restaurant'}
OPENER = 'いらっしゃいませ。何を飲みますか？'


def prepare(state, reply=OPENER):
    state['reply'] = json.dumps({'reply': reply, 'correction': None, 'exercise': {
        'target': 'コーヒー', 'prompt': '「コーヒー」 nghĩa là gì?', 'answer': 'Cà phê',
    }}, ensure_ascii=False)


def requests_to_ollama(state):
    return [json.loads(r.content) for r in state['requests'] if r.url.path == '/api/chat']


def test_practice_start_returns_unique_session_and_plays_only_dialogue(system):
    client, state, _ = system
    prepare(state)
    response = client.post('/practice-sessions', json=PREFERENCES)
    assert response.status_code == 201
    data = response.json()
    assert re.fullmatch(r'practice-[a-f0-9]{32}', data['session_id'])
    assert data['reply'] == OPENER and data['source'] == 'ollama'
    assert data['learning']['exercise']['answer'] == 'Cà phê'
    assert client.get(data['audio_url']).content == wav_bytes()
    assert [r.url.params['text'] for r in state['requests'] if r.url.path == '/audio_query'] == [OPENER]


def test_practice_text_and_voice_share_preferences_and_history(system):
    client, state, _ = system
    prepare(state)
    session = client.post('/practice-sessions', json=PREFERENCES).json()['session_id']
    prepare(state, 'はい、お茶ですね。温かいお茶ですか？')
    assert chat(client, 'お茶', session).json()['source'] == 'ollama'
    response = voice_chat(client, content=wav_bytes(), session=session)
    assert response.status_code == 200 and response.json()['learning']['exercise']
    opening, typed, spoken = requests_to_ollama(state)
    assert all(not p['think'] and not p['stream'] and p['format']['type'] == 'object' for p in (opening, typed, spoken))
    assert all(p['options']['stop'] == [] and p['options']['num_predict'] >= 512 for p in (opening, typed, spoken))
    assert all(key in opening['messages'][0]['content'] for key in PREFERENCES.values())
    assert typed['messages'][0] == spoken['messages'][0]
    assert spoken['messages'][1:] == [
        {'role': 'assistant', 'content': OPENER}, {'role': 'user', 'content': 'お茶'},
        {'role': 'assistant', 'content': 'はい、お茶ですね。温かいお茶ですか？'},
        {'role': 'user', 'content': response.json()['transcript']},
    ]


def test_new_practice_starts_with_clean_history(system):
    client, state, _ = system
    prepare(state)
    one = client.post('/practice-sessions', json=PREFERENCES).json()['session_id']
    chat(client, 'お茶', one)
    two = client.post('/practice-sessions', json={'level': 'N2', 'script': 'kanji', 'topic': 'work'}).json()['session_id']
    assert one != two and len(requests_to_ollama(state)[-1]['messages']) == 2


@pytest.mark.parametrize('change', [{'level': 'N9'}, {'topic': 'unknown'}, {'script': 'romaji'}, {'extra': True}])
def test_invalid_preferences_stop_before_external_calls(system, change):
    client, state, _ = system
    assert client.post('/practice-sessions', json=PREFERENCES | change).status_code == 422
    assert state['requests'] == []


def test_deleted_practice_session_returns_410(system):
    client, state, _ = system
    prepare(state)
    session = client.post('/practice-sessions', json=PREFERENCES).json()['session_id']
    client.delete('/sessions/' + session)
    state['requests'].clear()
    client.app.state.transcriber = None
    assert chat(client, 'お茶', session).status_code == 410
    assert voice_chat(client, content=wav_bytes(), session=session).status_code == 410
    assert state['requests'] == []


def test_deletion_during_transcription_prevents_practice_turn(system, monkeypatch):
    client, state, _ = system
    prepare(state)
    session = client.post('/practice-sessions', json=PREFERENCES).json()['session_id']
    state['requests'].clear()

    def transcribe(*args):
        assert client.delete('/sessions/' + session).status_code == 200
        return 'お茶'

    monkeypatch.setattr('server.transcribe_japanese', transcribe)
    assert voice_chat(client, content=wav_bytes(), session=session).status_code == 410
    assert state['requests'] == []


def test_failed_opening_releases_capacity(system):
    client, state, _ = system
    chat(client, session='used1')
    chat(client, session='used2')
    assert client.post('/practice-sessions', json=PREFERENCES).status_code == 502
    prepare(state)
    assert client.post('/practice-sessions', json=PREFERENCES).status_code == 201


def test_practice_keeps_dialogue_when_voicevox_is_offline(system):
    client, state, _ = system
    prepare(state)
    state['voicevox'] = 'offline'
    response = client.post('/practice-sessions', json=PREFERENCES)
    assert response.status_code == 201
    assert response.json()['reply'] == OPENER and response.json()['learning']['exercise']
    assert response.json()['audio_url'] is None and response.json()['error_audio']


def test_legacy_response_preserves_old_fields_with_additive_translation(system):
    client, _, _ = system
    expected = {'reply', 'audio_url', 'source', 'session_id', 'error_audio', 'translation', 'error_translation'}
    assert chat(client).json().keys() == expected
    assert voice_chat(client, content=wav_bytes()).json().keys() == expected | {'transcript'}


def test_nested_structured_reply_never_reaches_voicevox(system):
    client, state, _ = system
    state['reply'] = json.dumps({'reply': json.dumps({'reply': 'こんにちは。', 'correction': '説明です。'}, ensure_ascii=False)})
    assert client.post('/practice-sessions', json=PREFERENCES).status_code == 502
    assert not any(r.url.path in {'/audio_query', '/synthesis'} for r in state['requests'])


def test_expired_practice_does_not_become_generic_chat(system):
    client, state, settings = system
    prepare(state)
    session = client.post('/practice-sessions', json=PREFERENCES).json()['session_id']
    client.app.state.sessions[session].last_used -= settings.session_ttl + 1
    state['requests'].clear()
    assert chat(client, 'お茶', session).status_code == 410
    assert state['requests'] == []


def test_all_reply_types_translate_only_final_dialogue(system):
    client, state, _ = system
    rule = chat(client).json()
    prepare(state)
    practice = client.post('/practice-sessions', json=PREFERENCES).json()
    session = practice['session_id']
    prepare(state, 'はい、コーヒーですね。温かいものですか？')
    typed = chat(client, 'LEARNER PRIVATE INPUT', session).json()
    prepare(state, 'そうですね。今日はどうでしたか？')
    spoken = voice_chat(client, content=wav_bytes(), session=session).json()
    replies = [rule, practice, typed, spoken]
    assert all(r['translation'] == 'Bản dịch tiếng Việt.' and r['error_translation'] is None for r in replies)
    google = [r for r in state['requests'] if r.url.host == 'translate.googleapis.com']
    assert [r.url.params['q'] for r in google] == [r['reply'] for r in replies]
    assert all(set(r.url.params) == {'client', 'sl', 'tl', 'dt', 'q'} for r in google)
    assert all(r.url.params['sl'] == 'ja' and r.url.params['tl'] == 'vi' for r in google)
    assert [r.url.params['text'] for r in state['requests'] if r.url.path == '/audio_query'] == [r['reply'] for r in replies]


@pytest.mark.parametrize('mode', ['offline', 'timeout', 'blocked', 'malformed'])
def test_translation_failure_preserves_lesson_reply_audio_and_feedback(system, mode):
    client, state, _ = system
    state['translation'] = mode
    prepare(state)
    response = client.post('/practice-sessions', json=PREFERENCES)
    assert response.status_code == 201
    data = response.json()
    assert data['reply'] == OPENER and data['translation'] is None and data['error_translation']
    assert data['learning']['exercise']
    assert client.get(data['audio_url']).content == wav_bytes()


def test_health_never_calls_google(system):
    client, state, _ = system
    assert client.get('/health').status_code == 200
    assert not any(r.url.host == 'translate.googleapis.com' for r in state['requests'])


def test_translation_can_be_disabled_without_google_request(tmp_path):
    from server import Settings, create_app
    from test_api import FakeSpeechTranscriber
    from fastapi.testclient import TestClient
    import httpx
    requests = []
    def offline(request):
        requests.append(request)
        raise httpx.ConnectError('offline', request=request)
    app = create_app(Settings(audio_dir=tmp_path / 'audio', translation_enabled=False),
                     transport=httpx.MockTransport(offline), transcriber=FakeSpeechTranscriber())
    with TestClient(app) as client:
        response = chat(client)
        assert response.status_code == 200
        assert response.json()['translation'] is None and response.json()['error_translation'] is None
    assert not any(r.url.host == 'translate.googleapis.com' for r in requests)


def test_translation_disable_setting_comes_from_environment(monkeypatch):
    from server import Settings
    monkeypatch.setenv('TRANSLATION_ENABLED', '0')
    assert Settings.from_env().translation_enabled is False


def test_translation_and_speech_start_concurrently(system, monkeypatch):
    import asyncio
    client, _, _ = system
    audio_started = asyncio.Event()
    translation_started = asyncio.Event()

    async def synthesize(*args):
        audio_started.set()
        await asyncio.wait_for(translation_started.wait(), 0.5)
        return None, 'Audio fixture'

    class Translator:
        async def translate(self, reply):
            await asyncio.wait_for(audio_started.wait(), 0.5)
            translation_started.set()
            return 'Bản dịch song song', None

    monkeypatch.setattr('server.synthesize', synthesize)
    client.app.state.translator = Translator()
    response = chat(client)
    assert response.status_code == 200
    assert response.json()['translation'] == 'Bản dịch song song'
    assert response.json()['reply'] == 'ホットとアイス、どちらにしますか？'

QUICK_LESSON_IDS = ('order-food', 'introduce-yourself', 'ask-directions')


def test_quick_lessons_are_exposed_from_backend_source_of_truth(system):
    client, state, _ = system
    response = client.get('/lessons')
    assert response.status_code == 200
    lessons = response.json()['lessons']
    assert [lesson['id'] for lesson in lessons] == list(QUICK_LESSON_IDS)
    assert [lesson['level'] for lesson in lessons] == ['N5', 'N5', 'N4']
    assert [lesson['topic'] for lesson in lessons] == ['restaurant', 'introductions', 'travel']
    assert all(lesson['goal'] and lesson['label'] for lesson in lessons)
    assert state['requests'] == []


@pytest.mark.parametrize('lesson_id', QUICK_LESSON_IDS)
def test_quick_lesson_starts_with_progress_zero(system, lesson_id):
    client, state, _ = system
    prepare(state)
    response = client.post('/practice-sessions', json={'lesson_id': lesson_id})
    assert response.status_code == 201
    assert response.json()['progress']['lesson_id'] == lesson_id
    assert response.json()['progress']['completed_turns'] == 0
    assert response.json()['progress']['total_turns'] == 5
    assert response.json()['progress']['completed'] is False


def test_unknown_quick_lesson_is_rejected_before_ollama(system):
    client, state, _ = system
    response = client.post('/practice-sessions', json={'lesson_id': 'unknown-lesson'})
    assert response.status_code == 422
    assert state['requests'] == []


def test_quick_lesson_counts_non_empty_input_and_rejects_sixth_turn(system):
    client, state, _ = system
    prepare(state)
    session = client.post('/practice-sessions', json={'lesson_id': 'order-food'}).json()['session_id']
    for count in range(1, 6):
        prepare(state, f'はい、{count}回目です。')
        response = chat(client, 'Xin chào', session)
        assert response.status_code == 200
        assert response.json()['progress']['completed_turns'] == count
        assert response.json()['progress']['completed'] is (count == 5)
    prepare(state, 'もう一度。')
    response = chat(client, '六回目', session)
    assert response.status_code == 409
    assert response.json()['detail']


def test_failed_quick_lesson_turn_is_not_in_history_or_progress(system):
    client, state, _ = system
    prepare(state)
    session = client.post('/practice-sessions', json={'lesson_id': 'order-food'}).json()['session_id']
    state['reply'] = json.dumps({'reply': 'not Japanese'})
    response = chat(client, 'Xin chào', session)
    assert response.status_code == 502
    stored = client.app.state.sessions[session]
    assert stored.history == []
    assert stored.completed_turns == 0


def test_audio_or_translation_failure_keeps_successful_quick_lesson_turn(system):
    client, state, _ = system
    prepare(state)
    session = client.post('/practice-sessions', json={'lesson_id': 'order-food'}).json()['session_id']
    state['voicevox'] = 'offline'
    state['translation'] = 'offline'
    prepare(state, 'はい、わかりました。')
    response = chat(client, 'Tôi muốn trà', session)
    assert response.status_code == 200
    assert response.json()['progress']['completed_turns'] == 1
    stored = client.app.state.sessions[session]
    assert stored.completed_turns == 1
    assert stored.history[-2:] == [
        {'role': 'user', 'content': 'Tôi muốn trà'},
        {'role': 'assistant', 'content': 'はい、わかりました。'},
    ]


def test_completed_quick_lesson_rejects_concurrent_sixth_turn(tmp_path):
    import asyncio
    from server import Settings, create_app
    from test_api import FakeSpeechTranscriber

    async def scenario():
        requests = []

        async def upstream(request):
            requests.append(request)
            if request.url.host == 'ollama.test':
                if request.url.path == '/api/tags':
                    return httpx.Response(200, json={'models': [{'name': 'japanese-tutor:latest'}]})
                return httpx.Response(200, json={'message': {'content': json.dumps({'reply': 'はい、そうです。', 'correction': None, 'exercise': None}, ensure_ascii=False)}})
            if request.url.host == 'voicevox.test':
                if request.url.path == '/version':
                    return httpx.Response(200, json='test-version')
                if request.url.path == '/audio_query':
                    return httpx.Response(200, json={'accent_phrases': []})
                return httpx.Response(200, content=wav_bytes(), headers={'content-type': 'audio/wav'})
            raise AssertionError(request.url)

        settings = Settings(ollama_url='http://ollama.test', voicevox_url='http://voicevox.test',
                            audio_dir=tmp_path / 'audio', translation_enabled=False)
        app = create_app(settings, transport=httpx.MockTransport(upstream), transcriber=FakeSpeechTranscriber())
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://testserver') as client:
                started = await client.post('/practice-sessions', json={'lesson_id': 'order-food'})
                session = started.json()['session_id']
                for _ in range(4):
                    assert (await client.post('/chat', json={'text': '一回です。', 'session_id': session})).status_code == 200
                results = await asyncio.gather(*[
                    client.post('/chat', json={'text': '最後です。', 'session_id': session}) for _ in range(2)
                ])
                assert sorted(response.status_code for response in results) == [200, 409]
                assert app.state.sessions[session].completed_turns == 5

    asyncio.run(scenario())
