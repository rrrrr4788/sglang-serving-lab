# Basic overload protection

Configured on 2026-10-23 for the local single-GPU lab:

- `--max-running-requests 8`
- `--max-queued-requests 16`
- `SGLANG_REQ_WAITING_TIMEOUT=5` (seconds)

These are initial protective settings, not an established optimal capacity.
The scheduler queue is bounded; this does not provide per-user rate limiting or bound
all HTTP/tokenization work before scheduling. Queue-full rejection in this pinned
version uses 503, not 429. Streaming clients must also handle error events.

## One controlled check

Sent 32 concurrent authenticated non-streaming `/generate` requests with distinct
short synthetic prompts, `max_new_tokens=128`, `temperature=0`, and `ignore_eos=true`.

| Outcome | Count |
| --- | ---: |
| HTTP 200 | 24 |
| HTTP 503, queue-full error | 8 |
| Transport errors or other HTTP status | 0 |

The run completed in 2.55 seconds. The existing authentication/inference smoke check
passed immediately afterwards. This is a functional overload check, not a throughput
benchmark or a full reliability test.

The queue timeout was unset during that burst. Its missing environment entry was
subsequently added to Compose. A request actually exceeding the five-second waiting
limit has not been tested; queue-full rejection does not prove timeout behavior.
After recreating only SGLang, the container reported healthy, its environment
contained the five-second timeout, and the authentication/inference smoke check passed.

## Apply changes

```bash
docker compose up -d --no-deps --wait --wait-timeout 300 sglang
python3 scripts/smoke.py
```

Wait for readiness: `Started` alone does not mean model initialization has finished.
The smoke script needs the private API key exported in the shell, as in the README.
