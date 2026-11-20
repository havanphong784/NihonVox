"""Loopback-only integration fixture. WAV is a test tone, NOT VOICEVOX speech.

Run: .venv/bin/python -m uvicorn --app-dir tests stub_services:app --port 18021
Never use this module as the production speech service.
"""
import io
import math
import struct
import wave

from fastapi import FastAPI, Request
from fastapi.responses import Response

app = FastAPI()
requests_seen = []


@app.get('/version')
def version():
    return 'integration-test-tone-only'


@app.post('/audio_query')
def audio_query(speaker: int, text: str):
    requests_seen.append({'path': '/audio_query', 'speaker': speaker, 'text': text})
    return {'accent_phrases': [], 'speedScale': 1.0}


@app.post('/synthesis')
async def synthesis(request: Request, speaker: int):
    query = await request.json()
    requests_seen.append({'path': '/synthesis', 'speaker': speaker, 'query': query})
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(24000)
        audio.writeframes(b''.join(struct.pack('<h', int(2200 * math.sin(2 * math.pi * 440 * i / 24000)))
                                   for i in range(9600)))
    return Response(buffer.getvalue(), media_type='audio/wav')


@app.get('/__requests')
def requests():
    return requests_seen
