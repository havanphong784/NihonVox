"""Learning preferences and validation of structured local tutor output."""

import json
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict


class LearningPreferences(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    level: Literal['N5', 'N4', 'N3', 'N2', 'N1'] = 'N5'
    script: Literal['hiragana', 'katakana', 'kanji'] = 'hiragana'
    topic: Literal['daily', 'introductions', 'family', 'school', 'work', 'hobbies',
                   'restaurant', 'shopping', 'travel', 'weather', 'jlpt', 'free'] = 'daily'


class LessonExercise(BaseModel):
    prompt: str
    answer: str


class LearningFeedback(BaseModel):
    correction: str | None = None
    exercise: LessonExercise | None = None


class TutorReply(BaseModel):
    reply: str
    learning: LearningFeedback | None = None


class LessonPreset(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    id: str
    label: str
    level: Literal['N5', 'N4', 'N3', 'N2', 'N1']
    script: Literal['hiragana', 'katakana', 'kanji']
    topic: str
    goal: str
    context: str
    practice_sentence_japanese: str
    practice_sentence_vietnamese: str


LESSON_PRESETS = (
    LessonPreset(
        id='order-food', label='Gọi món', level='N5', script='hiragana', topic='restaurant',
        goal='Gọi một món và trả lời câu hỏi đơn giản ở quán ăn.',
        context='Bạn là khách gọi món tại quán cà phê; hãy hỏi món, số lượng hoặc nóng/lạnh bằng câu ngắn.',
        practice_sentence_japanese='コーヒーを一つお願いします。',
        practice_sentence_vietnamese='Cho tôi một ly cà phê.',
    ),
    LessonPreset(
        id='introduce-yourself', label='Tự giới thiệu', level='N5', script='hiragana', topic='introductions',
        goal='Giới thiệu bản thân và chia sẻ một sở thích.',
        context='Bạn đang gặp một người bạn Nhật lần đầu; hãy nói tên, quê quán hoặc sở thích bằng câu ngắn.',
        practice_sentence_japanese='ベトナムから来ました。音楽が好きです。',
        practice_sentence_vietnamese='Tôi đến từ Việt Nam. Tôi thích âm nhạc.',
    ),
    LessonPreset(
        id='ask-directions', label='Hỏi đường', level='N4', script='hiragana', topic='travel',
        goal='Hỏi đường và xác nhận một chỉ dẫn đơn giản.',
        context='Bạn đang ở gần ga tàu; hãy hỏi đường đến một địa điểm và xác nhận hướng đi.',
        practice_sentence_japanese='駅はどこですか。',
        practice_sentence_vietnamese='Nhà ga ở đâu vậy?',
    ),
)
LESSON_BY_ID = {lesson.id: lesson for lesson in LESSON_PRESETS}


def get_lesson_preset(lesson_id: str) -> LessonPreset:
    try:
        return LESSON_BY_ID[lesson_id]
    except KeyError as exc:
        raise ValueError('Bài luyện nhanh không hợp lệ.') from exc


TOPICS = dict(daily='日常会話', introductions='自己紹介', family='家族', school='学校',
              work='仕事', hobbies='趣味', restaurant='飲食店・カフェ', shopping='買い物',
              travel='旅行', weather='天気', jlpt='日本語能力試験', free='自由な話題')
LEVELS = dict(N5='ごく基本的な語彙と文法。短く簡単な質問', N4='身近な語彙と基本的な文法',
              N3='日常的な話題に理由や経験を加える', N2='自然な語彙で意見や理由を掘り下げる',
              N1='文脈に応じた表現やニュアンスを使う')
SCRIPTS = {'hiragana': r'[ぁ-ゖ]', 'katakana': r'[ァ-ヺ]', 'kanji': r'[㐀-鿿]'}
KANA = re.compile(r'[ぁ-ゖァ-ヺ]')
JAPANESE = re.compile(r'[ぁ-ゖァ-ヺ㐀-鿿]')
TUTOR_FORMAT = {
    'type': 'object', 'required': ['reply', 'correction', 'exercise'],
    'properties': {
        'reply': {'type': 'string'},
        'correction': {'type': ['string', 'null']},
        'exercise': {'type': ['object', 'null'], 'required': ['target', 'prompt', 'answer'],
                     'properties': {key: {'type': 'string'} for key in ('target', 'prompt', 'answer')},
                     'additionalProperties': False},
    },
    'additionalProperties': False,
}


def build_tutor_prompt(preferences: LearningPreferences, *, opening: bool, lesson: LessonPreset | None = None) -> str:
    level, script, topic = preferences.level, preferences.script, preferences.topic
    action = (
        '話題に合う質問またはロールプレイの最初の台詞から始める。correction は null。'
        if opening else
        '学習者の発言の具体的な内容に反応し、自然な場合は関連する質問を一つする。'
        '正しい文は訂正しない。意味のある文法・語彙の改善があるときだけ correction に短くベトナム語で説明する。'
        'それ以外は null。発音の評価はしない。'
    )
    return (
        f'あなたは日本語会話の先生。レベル: {level}（{LEVELS[level]}）。話題: {topic}（{TOPICS[topic]}）。\n'
        'JSONで reply, correction, exercise を返す。reply は音声で読む自然な日本語の台詞だけ、短い1〜2文。'
        f'文字練習の指定で reply の表記を変えない。{action}\n'
        f'exercise は {script} の練習を一問。話題・台詞に関係のある語を選ぶ。'
        f'target に {script} の文字を含む練習対象、prompt にその target をそのまま含むベトナム語の問題、'
        'answer に正しい読みまたはベトナム語の意味を書く。必ず prompt の中に target の日本語をそのまま書く。'
        '例: target=コーヒー, prompt=「コーヒー」 nghĩa là gì?, answer=Cà phê。'
        '答えを問題に含めない。適切な問題を作れなければ exercise は null。'
        + (f'\n今回の短い練習目標: {lesson.goal}。役割と場面: {lesson.context}。' if lesson else '')
    )


def _optional_text(value, limit: int) -> str | None:
    if isinstance(value, str):
        value = value.strip()
        if value and len(value) <= limit:
            return value
    return None


def parse_tutor_reply(content: str, preferences: LearningPreferences, *, opening: bool) -> TutorReply:
    data = json.loads(content)
    if not isinstance(data, dict) or not isinstance(data.get('reply'), str):
        raise ValueError('Missing tutor dialogue')
    # Count punctuation runs once (e.g. ！？) and preserve unfinished final sentences.
    dialogue = data['reply'].strip()
    if (any(marker in dialogue for marker in ('{', '}', '```', '<think', '</think'))
            or dialogue.startswith('[')
            or re.search(r'"(?:reply|correction|exercise)"\s*:', dialogue)):
        raise ValueError('Structured content is not spoken dialogue')
    sentences = [part.strip() for part in re.findall(r'[^。！？?!]+[。！？?!]*', dialogue)
                 if JAPANESE.search(part)]
    reply = ''.join(sentences[:2])
    if not reply or not KANA.search(reply) or len(reply) > 400:
        raise ValueError('Unusable tutor dialogue')

    correction = None if opening else _optional_text(data.get('correction'), 400)
    exercise = None
    raw = data.get('exercise')
    if isinstance(raw, dict):
        target = _optional_text(raw.get('target'), 80)
        prompt = _optional_text(raw.get('prompt'), 300)
        answer = _optional_text(raw.get('answer'), 300)
        if target and prompt and answer and target in prompt and re.search(SCRIPTS[preferences.script], target):
            exercise = LessonExercise(prompt=prompt, answer=answer)
    learning = LearningFeedback(correction=correction, exercise=exercise) if correction or exercise else None
    return TutorReply(reply=reply, learning=learning)
