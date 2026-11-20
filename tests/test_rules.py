import pytest


@pytest.mark.parametrize(('text', 'expected'), [
    ('お茶', 'ホットとアイス、どちらにしますか？'),
    ('おちゃ', 'ホットとアイス、どちらにしますか？'),
    ('コーヒー', 'ホットとアイス、どちらにしますか？'),
    ('コーヒーをください', 'ホットとアイス、どちらにしますか？'),
    ('アイス', 'かしこまりました。'),
    ('アイスで', 'かしこまりました。'),
    ('  お茶。\n', 'ホットとアイス、どちらにしますか？'),
    ('ｺｰﾋｰ', 'ホットとアイス、どちらにしますか？'),
    ('今日はいい天気ですね。', None),
    ('お茶とケーキ', None),
    ('', None),
])
def test_rule_matching(text, expected):
    from server import match_rule
    assert match_rule(text) == expected


@pytest.mark.parametrize(('text', 'expected'), [
    ('いい天気ですね。散歩しましょう。', 'いい天気ですね。'),
    ('何を飲みますか？お茶ですか？', '何を飲みますか？'),
    ('すごい！そうですね。', 'すごい！'),
    ('何ですか?教えてください。', '何ですか?'),
    ('いいですね!行きましょう。', 'いいですね!'),
    ('まだ続いている文', 'まだ続いている文'),
    ('\n  こんにちは。\n説明です。 ', 'こんにちは。'),
    ('Sure!\nこんにちは。Hello.', 'こんにちは。'),
    ('<think>考えています。</think>こんにちは。', 'こんにちは。'),
    ('```text\nこんにちは。\n```', 'こんにちは。'),
])
def test_extracts_first_japanese_sentence_without_mid_sentence_cut(text, expected):
    from server import first_japanese_sentence
    assert first_japanese_sentence(text) == expected


@pytest.mark.parametrize('text', ['', ' \n ', 'Hello, how are you?', '<think>考え中</think>'])
def test_empty_or_non_japanese_reply_is_rejected(text):
    from server import first_japanese_sentence
    with pytest.raises(ValueError):
        first_japanese_sentence(text)
