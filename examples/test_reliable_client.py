# Fast local HTTP simulations; no GPU or live service required.
import asyncio
import unittest
from unittest.mock import patch

import httpx
from reliable_client import BudgetExceeded, CallFailed, complete


class ClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_503_then_success(self):
        calls = []
        async def handle(request):
            calls.append(request)
            if len(calls) == 1:
                return httpx.Response(503)
            return httpx.Response(200, json={'choices': [{'message': {'content': 'hello'}}]})
        with patch('reliable_client.random.uniform', return_value=0):
            result = await complete('hello', api_key='test-only', transport=httpx.MockTransport(handle))
        self.assertEqual(result.attempts, 2)
        self.assertEqual(result.response['choices'][0]['message']['content'], 'hello')

    async def test_401_is_not_retried(self):
        calls = []
        async def handle(request):
            calls.append(request)
            return httpx.Response(401)
        with self.assertRaises(CallFailed) as failure:
            await complete('hello', api_key='test-only', transport=httpx.MockTransport(handle))
        self.assertEqual(failure.exception.status, 401)
        self.assertEqual(len(calls), 1)

    async def test_retry_limit(self):
        calls = []
        async def handle(request):
            calls.append(request)
            return httpx.Response(503)
        with patch('reliable_client.random.uniform', return_value=0):
            with self.assertRaises(CallFailed) as failure:
                await complete('hello', api_key='test-only', max_retries=2,
                               transport=httpx.MockTransport(handle))
        self.assertEqual(failure.exception.status, 503)
        self.assertEqual(len(calls), 3)

    async def test_budget_cancels_inflight_request(self):
        cancelled = asyncio.Event()
        async def handle(request):
            try:
                await asyncio.sleep(60)
            finally:
                cancelled.set()
        with self.assertRaises(BudgetExceeded) as failure:
            await complete('hello', api_key='test-only', total_timeout=0.05,
                           transport=httpx.MockTransport(handle))
        self.assertEqual(failure.exception.attempts, 1)
        self.assertTrue(cancelled.is_set())

    async def test_budget_includes_retry_after_wait(self):
        calls = []
        async def handle(request):
            calls.append(request)
            return httpx.Response(503, headers={'Retry-After': '60'})
        with self.assertRaises(BudgetExceeded):
            await complete('hello', api_key='test-only', total_timeout=0.05,
                           transport=httpx.MockTransport(handle))
        self.assertEqual(len(calls), 1)

    async def test_read_failure_is_not_replayed(self):
        calls = []
        async def handle(request):
            calls.append(request)
            raise httpx.ReadError('simulated connection reset', request=request)
        with self.assertRaises(CallFailed):
            await complete('hello', api_key='test-only', transport=httpx.MockTransport(handle))
        self.assertEqual(len(calls), 1)


if __name__ == '__main__':
    unittest.main()
