import json
import re

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


def test_legacy_response_fields_do_not_change(system):
    client, _, _ = system
    expected = {'reply', 'audio_url', 'source', 'session_id', 'error_audio'}
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
