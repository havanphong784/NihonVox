import asyncio
import json

import httpx
import pytest


def test_google_request_joins_segments_and_caches_success():
    from translation import GoogleTranslator

    async def scenario():
        requests = []
        def upstream(request):
            requests.append(request)
            return httpx.Response(200, json=[[
                ['Hôm nay trời đẹp.', '今日は晴れです。'], [' Bạn khỏe không?', 'お元気ですか？'],
            ], None, 'ja'])
        async with httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as client:
            translator = GoogleTranslator(client)
            reply = '今日は晴れです。お元気ですか？'
            assert await translator.translate(reply) == ('Hôm nay trời đẹp. Bạn khỏe không?', None)
            assert await translator.translate(reply) == ('Hôm nay trời đẹp. Bạn khỏe không?', None)
        assert len(requests) == 1
        request = requests[0]
        assert request.url.host == 'translate.googleapis.com'
        assert request.url.path == '/translate_a/single'
        assert request.method == 'GET'
        assert dict(request.url.params) == {'client': 'gtx', 'sl': 'ja', 'tl': 'vi', 'dt': 't', 'q': reply}
    asyncio.run(scenario())


@pytest.mark.parametrize('response', [
    httpx.Response(429), httpx.Response(503), httpx.Response(302, headers={'location': 'https://another.test'}),
    httpx.Response(200, text='<html>blocked</html>'),
    httpx.Response(200, json={}), httpx.Response(200, json=[None]),
    httpx.Response(200, json=[[]]), httpx.Response(200, json=[[[None, '日本語']]]),
    httpx.Response(200, json=[[['', '日本語']]]),
    httpx.Response(200, json=[[['Xin chào', 'こんにちは'], [5, '世界']]]),
    httpx.Response(200, json=[[['x' * 8001, '日本語']]]),
    httpx.Response(200, content=b'x' * (64 * 1024 + 1)),
])
def test_google_failure_is_nonfatal_and_not_cached(response):
    from translation import GoogleTranslator

    async def scenario():
        calls = []
        def upstream(request):
            calls.append(request)
            return response if len(calls) == 1 else httpx.Response(200, json=[[['Xin chào', 'こんにちは']]])
        async with httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as client:
            translator = GoogleTranslator(client)
            translated, notice = await translator.translate('こんにちは')
            assert translated is None and notice and 'Google' in notice
            assert await translator.translate('こんにちは') == ('Xin chào', None)
            assert len(calls) == 2
    asyncio.run(scenario())


def test_cache_expiry_and_lru_eviction(monkeypatch):
    from translation import GoogleTranslator
    now = [0.0]
    monkeypatch.setattr('translation.time.monotonic', lambda: now[0])

    async def scenario():
        calls = []
        def upstream(request):
            calls.append(request.url.params['q'])
            return httpx.Response(200, json=[[['Bản dịch', '日本語']]])
        async with httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as client:
            translator = GoogleTranslator(client, cache_size=2, cache_ttl=10)
            for reply in ['一', '二', '一', '三', '一', '二']:
                await translator.translate(reply)
            assert calls == ['一', '二', '三', '二']
            now[0] = 11
            await translator.translate('二')
            assert calls == ['一', '二', '三', '二', '二']
    asyncio.run(scenario())


def test_network_errors_and_hard_deadline_are_nonfatal():
    from translation import GoogleTranslator

    async def scenario():
        async def slow(request):
            await asyncio.Event().wait()
        async with httpx.AsyncClient(transport=httpx.MockTransport(slow)) as client:
            result, notice = await GoogleTranslator(client, timeout=0.01).translate('こんにちは')
            assert result is None and notice
        def offline(request):
            raise httpx.ConnectError('offline', request=request)
        async with httpx.AsyncClient(transport=httpx.MockTransport(offline)) as client:
            result, notice = await GoogleTranslator(client).translate('こんにちは')
            assert result is None and notice
    asyncio.run(scenario())


def test_disabled_or_empty_input_never_calls_google():
    from translation import GoogleTranslator

    async def scenario():
        def unexpected(request):
            raise AssertionError('No request expected')
        async with httpx.AsyncClient(transport=httpx.MockTransport(unexpected)) as client:
            assert await GoogleTranslator(client, enabled=False).translate('こんにちは') == (None, None)
            result, notice = await GoogleTranslator(client).translate('')
            assert result is None
    asyncio.run(scenario())


def test_cancellation_is_propagated():
    from translation import GoogleTranslator

    async def scenario():
        started = asyncio.Event()
        async def upstream(request):
            started.set()
            await asyncio.Event().wait()
        async with httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as client:
            task = asyncio.create_task(GoogleTranslator(client).translate('こんにちは'))
            await started.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
    asyncio.run(scenario())
