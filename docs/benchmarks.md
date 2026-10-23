# Benchmark methodology

## Historical evidence

Six logs were found under `~/sglang-benchmarks`: four length-sweep runs and two prefix
cache runs. No standalone benchmark scripts were found in that directory or the
initial repository. `benchmarks/run.py` is new, reconstructed from their saved
`Namespace` arguments. The concurrency sweep is new and has no imported result.

The imported logs use `Qwen/Qwen3-0.6B`, seed 42, max concurrency 8, unlimited offered
request rate, one warmup request, temperature 0, and streaming. They are synthetic
experiments. Their original GPU, driver, model revision, and image digest were not
recorded. The image observed during integration is not proof of the historical image.

| Suite | Workload |
| --- | --- |
| Length | 100 prompts; configured input/output pairs 128/128, 1024/128, 128/512, 1024/512; random range ratio 0 |
| Prefix unique | 64 groups × 1 prompt, configured system/question/output lengths 512/64/64 |
| Prefix shared | 1 group × 64 prompts, same configured lengths |
| New concurrency | 1, 2, 4, 8, 16 concurrent requests at configured lengths 128/128 |

Prefix runs use generated-shared-prefix with range ratio 1 and cache flush before
each run. The native benchmark warmup can populate the cache after that flush.
Flush operations require an idle server and fail if not authorized; the lab config
uses one API key and does not configure a separate admin key. If you add one, revise
benchmark/admin credential handling before running prefix tests.

## Interpretation limits

- Historical arguments contain `disable_ignore_eos=True`, so the runner explicitly
  allows EOS. Configured lengths are not exact generated lengths. The 128-output
  cases generated 6,316 tokens across 100 requests, not 12,800.
- The shared prefix run generated 3,793 tokens; unique generated 3,911. Their
  retokenized counts also differ from server token counts. Compare like-for-like
  throughput definitions; these are not a controlled proof of cache speedup.
- Single runs without repeated trials, error bars, hardware provenance, or isolation
  cannot establish general performance claims. Cache hit metrics were not saved in
  these logs, so lower TTFT alone cannot establish a measured hit rate.
- Native benchmark peak-concurrency statistics differ from the configured client
  limit in these logs. Values are preserved without treating them as admission-control
  guarantees.
- The new Compose requires API-key authentication; old logs used an unauthenticated
  local server. No new performance numbers were produced during integration.

For a stronger experiment, record exact GPU/driver/runtime/model revision, use a quiet
GPU, repeat both orders several times, fix the token policy, capture Prometheus metrics,
and report failures alongside latency and throughput. Record any CUDA Graph or cache
configuration change explicitly. Do not publish real prompts, auth headers, or tokens.
