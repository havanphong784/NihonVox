import json

import pytest


def test_prompt_targets_level_topic_and_separate_script():
    from tutor import LearningPreferences, build_tutor_prompt
    beginner = build_tutor_prompt(LearningPreferences(level='N5', script='katakana', topic='restaurant'), opening=False)
    advanced = build_tutor_prompt(LearningPreferences(level='N1', script='kanji', topic='work'), opening=False)
    assert all(value in beginner for value in ['N5', 'restaurant', 'katakana', '自然な日本語', 'ベトナム語'])
    assert all(value in advanced for value in ['N1', 'work', 'kanji'])
    assert '正しい文' in beginner


def parse(data, *, script='katakana', opening=False):
    from tutor import LearningPreferences, parse_tutor_reply
    return parse_tutor_reply(json.dumps(data, ensure_ascii=False), LearningPreferences(script=script), opening=opening)


@pytest.mark.parametrize(('text', 'expected'), [
    ('いいですね。何を飲みますか？また来てください。', 'いいですね。何を飲みますか？'),
    ('そうですか。次は何をしましょう', 'そうですか。次は何をしましょう'),
    ('いいですね！？何を飲みますか？', 'いいですね！？何を飲みますか？'),
])
def test_tutor_reply_keeps_acknowledgment_and_followup(text, expected):
    assert parse({'reply': text}).reply == expected


def test_invalid_learning_does_not_erase_reply():
    assert parse({'reply': 'お茶です。', 'correction': ['x'], 'exercise': {'answer': 5}}).learning is None
    lesson = parse({'reply': 'お茶です。', 'correction': 'Dùng trợ từ を.', 'exercise': {'answer': 5}}).learning
    assert lesson.correction == 'Dùng trợ từ を.' and lesson.exercise is None


@pytest.mark.parametrize(('script', 'target', 'wrong'), [
    ('katakana', 'コーヒー', '珈琲'), ('hiragana', 'おちゃ', '紅茶'), ('kanji', '映画', 'えいが'),
])
def test_exercise_requires_selected_script(script, target, wrong):
    def data(value, visible):
        return {'reply': '今日はいい天気ですね。', 'exercise': {'target': value, 'prompt': f'Đọc {visible}', 'answer': 'đáp án'}}
    lesson = parse(data(target, target), script=script).learning
    assert lesson.exercise.model_dump() == {'prompt': f'Đọc {target}', 'answer': 'đáp án'}
    assert parse(data(wrong, wrong), script=script).learning is None
    assert parse(data(target, wrong), script=script).learning is None


def test_opener_never_corrects_a_learner():
    assert parse({'reply': 'お元気ですか？', 'correction': 'Sai trợ từ.'}, opening=True).learning is None


@pytest.mark.parametrize('invalid', [{}, {'reply': 'Hello!'}, {'reply': 'あ' * 401}, {'reply': {'exercise': '日本語'}}])
def test_unusable_dialogue_is_rejected(invalid):
    with pytest.raises(ValueError):
        parse(invalid)


@pytest.mark.parametrize('reply', [
    '{"reply":"こんにちは。","correction":"日本語を直してください。"}',
    '["こんにちは。","追加の説明です。"]',
    '```json\n{"reply":"こんにちは。"}\n```',
])
def test_serialized_envelopes_are_never_tutor_dialogue(reply):
    with pytest.raises(ValueError):
        parse({'reply': reply})
