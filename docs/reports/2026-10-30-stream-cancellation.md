# HTTPS streaming and cancellation acceptance

Date:2026-10-30 America/Los_Angeles (raw filename uses UTC20261031T021727Z).
The operator ran the two-request helper; the assistant reviewed the actual8-event
JSONL. Private artifact stream-cancel-20261031T021727Z.jsonl,SHA256 `7663a83cdcf2778cd15e1b6ac1f4e1183782c29568350dcb850a844a990a5d4a`.

Both generation requests came from local WSL through trusted HTTPS,Traefik and the
fixed Gateway0.3.2 into the existing SGLang0.5.21 TP1/DP1 worker. The private engine
metrics side channel used the explicit cloud context through the SSH API tunnel.
No deployment,manual scale or explicit abort API was used. Other generation traffic
was stopped for the test; worker URL and cumulative metrics stayed stable.

## Complete SSE request

64 input token IDs,temperature0,ignore_eos=true,max128 output tokens. HTTP200 and
text/event-stream,request ID and monotonic token-count checks passed;128 native SSE
events delivered128 output tokens with a finish reason and [DONE]. Client TTFT was
288.069ms and E2E0.653s for this single sample,including the external request path;
these are not percentile/capacity/SLO results. The engine generation counter rose
450600→450728,exactly128;running/queued were0 afterward.

## Early disconnect request

The second request had the same64-token input and a3500-token output cap with EOS
ignored. After receiving32 output tokens,the client checked that the same engine
was still running1 request with queue0,and then closed its HTTPS response.

| Observation | Result |
| --- | --- |
| Immediately before close | running1,queued0;no natural finish seen |
| Abort counter before | No initialized sample (null,not assumed zero) |
| First post-close sample | running0,queued0,abort counter1 |
| Second post-close sample | running0,queued0,abort counter1 |
| Generation counter for the cancellation request |450728→451091:363 tokens total |
| Two-sample idle confirmation |2.427s after close,including observation overhead |

The first post-close sample arrived about1.0s after the close marker. This does not
measure an exact server abort latency; it includes tunnel/API/probe timing.
The new positive abort sample,request observed active before close,two idle samples
and generated count below3500 jointly support cancellation rather than merely a
client UI stopping or natural full-length completion.

363 is the total engine output count for the second request,not output produced
after disconnection. The client received32;generation/transport buffering and the
pre-close private probe allow the engine to advance further. The data cannot say
that331 tokens were generated after close. The original helper field was named
post_cancel_generated_tokens;raw evidence was preserved and the future helper field
was renamed cancel_request_generated_tokens without changing test behavior.

## Accepted scope and limits

One complete native SSE and one end-to-end early-disconnect cancellation passed.
Partial tokens received while the long request was still active also demonstrate
stream delivery before completion. Default CA/hostname verification stayed enabled,
redirects were rejected,and no credential or generated text was logged.

This proves clearance of the active request slot,not release of the preallocated
VRAM pool or an exact KV-cache byte count. Reusable prefixes and memory allocation
can remain. It does not cover cancellation under load,in-flight Pod shutdown,
node failure,or all supported API schemas. Worker drain,actionable alert,
controlled update/rollback and final paid-resource teardown remain pending.
