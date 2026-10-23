#!/usr/bin/env python3
# Non-streaming OpenAI-compatible client. Python 3.10+, httpx 0.28.1.
import argparse
import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import json
import math
import os
import random
import sys

import httpx


class CallFailed(RuntimeError):
    def __init__(self, message, *, attempts, status=None):
        super().__init__(message)
        self.attempts = attempts
        self.status = status


class BudgetExceeded(CallFailed):
    pass


@dataclass(frozen=True)
class Completion:
    response: dict
    attempts: int


def retry_after_seconds(value):
    if not value:
        return 0.0
    try:
        if value.strip().isdigit():
            return float(value.strip())
        when = parsedate_to_datetime(value)
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        return max(0.0, (when - datetime.now(timezone.utc)).total_seconds())
    except (ValueError, TypeError, OverflowError):
        return 0.0


async def complete(prompt, *, api_key, base_url='http://127.0.0.1:30000/v1',
                   model='Qwen/Qwen3-0.6B', total_timeout=15.0,
                   max_retries=2, max_tokens=32, transport=None):
    if not api_key or not api_key.strip():
        raise ValueError('Set SGLANG_API_KEY in the environment.')
    if not math.isfinite(total_timeout) or total_timeout <= 0:
        raise ValueError('total_timeout must be finite and positive.')
    if not isinstance(max_retries, int) or not 0 <= max_retries <= 10:
        raise ValueError('max_retries must be an integer from 0 to 10.')
    if max_tokens <= 0:
        raise ValueError('max_tokens must be positive.')
    url = httpx.URL(base_url.rstrip('/') + '/chat/completions')
    if url.scheme not in ('http', 'https') or not url.host or url.userinfo:
        raise ValueError('Use an HTTP(S) base URL without embedded credentials.')
    payload = {'model': model, 'messages': [{'role': 'user', 'content': prompt}],
               'max_tokens': max_tokens, 'temperature': 0, 'stream': False}
    attempts = 0

    async def run():
        nonlocal attempts
        # One async deadline outside this loop covers response bodies AND backoff.
        # No HTTPX phase timeout, environment proxy, hidden transport retries or redirects.
        async with httpx.AsyncClient(timeout=None, trust_env=False,
                                     follow_redirects=False, transport=transport) as client:
            while True:
                attempts += 1
                retry_after = 0.0
                try:
                    response = await client.post(
                        url, json=payload, headers={'Authorization': 'Bearer ' + api_key})
                except (httpx.ConnectError, httpx.ConnectTimeout):
                    if attempts > max_retries:
                        raise CallFailed('Connection failed; retry limit reached.',
                                         attempts=attempts) from None
                except httpx.TransportError:
                    # A read/write failure may occur after the server accepted work.
                    raise CallFailed('Transport failed; request outcome is uncertain. Not retried.',
                                     attempts=attempts) from None
                else:
                    if response.status_code != 503 or attempts > max_retries:
                        if not 200 <= response.status_code < 300:
                            raise CallFailed('HTTP ' + str(response.status_code) + '; call stopped.',
                                             attempts=attempts, status=response.status_code)
                        try:
                            data = response.json()
                            if not isinstance(data, dict) or not data.get('choices'):
                                raise ValueError()
                        except ValueError:
                            raise CallFailed('Invalid completion response; not retried.',
                                             attempts=attempts) from None
                        return Completion(data, attempts)
                    retry_after = retry_after_seconds(response.headers.get('Retry-After'))
                # Full jitter plus any server-requested minimum delay. The shared
                # deadline cancels even this sleep if the remaining budget runs out.
                delay = max(random.uniform(0, min(0.5 * 2 ** (attempts - 1), 4.0)),
                            retry_after)
                await asyncio.sleep(delay)

    try:
        return await asyncio.wait_for(run(), timeout=total_timeout)
    except asyncio.TimeoutError:
        raise BudgetExceeded('Total call budget exhausted; no further attempt.',
                             attempts=attempts) from None


def main():
    parser = argparse.ArgumentParser(description='Non-streaming inference with a shared deadline and bounded retries.')
    parser.add_argument('prompt')
    parser.add_argument('--base-url', default=os.environ.get('SGLANG_BASE_URL',
                        'http://127.0.0.1:' + os.environ.get('SGLANG_PORT', '30000') + '/v1'))
    parser.add_argument('--model', default=os.environ.get('MODEL_PATH', 'Qwen/Qwen3-0.6B'))
    parser.add_argument('--budget', type=float, default=15.0)
    parser.add_argument('--retries', type=int, default=2)
    parser.add_argument('--max-tokens', type=int, default=32)
    args = parser.parse_args()
    try:
        result = asyncio.run(complete(args.prompt, api_key=os.environ.get('SGLANG_API_KEY'),
                            base_url=args.base_url, model=args.model, total_timeout=args.budget,
                            max_retries=args.retries, max_tokens=args.max_tokens))
    except CallFailed as exc:
        print(f'ERROR: {exc} attempts={exc.attempts}', file=sys.stderr)
        return 1
    except (ValueError, httpx.InvalidURL) as exc:
        # Avoid reflecting a URL, prompt, or credentials in command errors.
        print('ERROR: Invalid configuration; check key, URL and numeric options.', file=sys.stderr)
        return 2
    print(json.dumps({'attempts': result.attempts, 'response': result.response}, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
