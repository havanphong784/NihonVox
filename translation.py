"""Best-effort Google Japanese-to-Vietnamese translation of final AI replies only.

This uses an unofficial, no-key endpoint. Network errors must never break chat.
Only successful translations are retained, in a bounded, short-lived RAM cache.
"""

import asyncio
import json
import time
from collections import OrderedDict

import httpx

GOOGLE_TRANSLATE_URL = 'https://translate.googleapis.com/translate_a/single'
MAX_RESPONSE_BYTES = 64 * 1024
TRANSLATION_NOTICE = 'Chưa dịch được bằng Google. Bạn vẫn có thể đọc hoặc nghe câu tiếng Nhật.'


class GoogleTranslator:
    def __init__(self, client: httpx.AsyncClient, *, enabled: bool = True, timeout: float = 6.0,
                 cache_size: int = 256, cache_ttl: float = 3600.0):
        self.client = client
        self.enabled = enabled
        self.timeout = timeout
        self.cache_size = cache_size
        self.cache_ttl = cache_ttl
        self._cache: OrderedDict[str, tuple[float, str]] = OrderedDict()

    async def translate(self, reply: str) -> tuple[str | None, str | None]:
        if not self.enabled:
            return None, None
        if not isinstance(reply, str) or not reply.strip() or len(reply) > 2000:
            return None, TRANSLATION_NOTICE
        now = time.monotonic()
        for key, (expires, _) in list(self._cache.items()):
            if expires <= now:
                self._cache.pop(key, None)
        if reply in self._cache:
            self._cache.move_to_end(reply)
            return self._cache[reply][1], None
        try:
            text = await asyncio.wait_for(self._fetch(reply), timeout=self.timeout)
        except (httpx.HTTPError, ValueError, TypeError, asyncio.TimeoutError):
            return None, TRANSLATION_NOTICE
        if self.cache_size > 0:
            self._cache[reply] = (time.monotonic() + self.cache_ttl, text)
            self._cache.move_to_end(reply)
            while len(self._cache) > self.cache_size:
                self._cache.popitem(last=False)
        return text, None

    async def _fetch(self, reply: str) -> str:
        params = {'client': 'gtx', 'sl': 'ja', 'tl': 'vi', 'dt': 't', 'q': reply}
        async with self.client.stream('GET', GOOGLE_TRANSLATE_URL, params=params,
                                      timeout=5.0, follow_redirects=False) as response:
            response.raise_for_status()
            body = bytearray()
            async for chunk in response.aiter_bytes():
                if len(body) + len(chunk) > MAX_RESPONSE_BYTES:
                    raise ValueError('Translation response too large')
                body.extend(chunk)
        data = json.loads(body)
        if not isinstance(data, list) or not data or not isinstance(data[0], list) or not data[0]:
            raise ValueError('Missing translation segments')
        pieces = []
        for segment in data[0]:
            if (not isinstance(segment, list) or not segment
                    or not isinstance(segment[0], str) or not segment[0].strip()):
                raise ValueError('Invalid translation segment')
            pieces.append(segment[0])
        text = ''.join(pieces).strip()
        if not text or len(text) > 8000:
            raise ValueError('Invalid translation text')
        return text
