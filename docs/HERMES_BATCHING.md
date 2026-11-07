# Hermes streaming jobs and reusable context

Measured November 6, 2026 (America/New_York) on the same eight Sparks, official DeepSeek-V4.1-Flash-1017, disk Engram, 10.5 GiB KV per rank and 2 GHz GPU cap. Hermes source commit: `2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19`. Private profiles isolated the tests from the operator's sessions, provider secrets, memory, messaging and shell tools.

## Five-policy comparison

Hermes used the tested model to call a local benchmark tool three times, inspect the results, and save a policy. Each block compared five strategies on the same 16 independent fixture jobs. Each job used normal streamed chat turns to read inputs, calculate a result and save a checked record exactly once. A separate, unmarked foreground agent sent its first request 150 ms after the worker release. Tool results were checked against their originating calls. All **240 background and 15 foreground jobs passed**, covering 765 model streams. The coach made another five model calls and four benchmark-tool calls outside the timed waves.

Prepare all clients before timing. Limit active background jobs to 8, 15 or 16 and refill each slot when a job ends. Regular dispatch uses the existing API. Coalesced dispatch marks background requests for a maximum 12 ms idle-only input-queue wait, collecting up to eight before a scheduler step. Any foreground or control message ends that wait immediately and is handled in arrival order. It does not preempt already scheduled GPU work. The sixteen-job option is a client concurrency limit, not a promise of a sixteen-request GPU batch.

| Background policy | Checked jobs per active hour, pooled | Whole-wave native tok/s, median | First usable foreground tool, median | Checked foreground result, median |
|---|---:|---:|---:|---:|
| 8 regular | 3,450 | 133.78 | 4.19 s | 11.95 s |
| 8 coalesced | 3,859 | 142.05 | **3.52 s** | **10.98 s** |
| 15 coalesced | 4,553 | 165.03 | 5.88 s | 11.90 s |
| 16 regular | 4,377 | 161.67 | 8.35 s | 13.03 s |
| 16 coalesced | **4,855** | **173.88** | 7.65 s | 11.93 s |

Each arm passed 48/48 background and 3/3 foreground jobs. At sixteen, coalescing raised the pooled checked job rate by 10.9% over regular dispatch; versus eight regular jobs the gain was 40.7%. Coalesced sixteen led every block, at 4,699–5,139 checked jobs per active hour. The first logged fresh-prefill groups were 5, 5 and 6 requests; regular sixteen started with one in each block.

Worker throughput is successful background jobs / time from worker release to last background outcome, pooled over three waves. This includes model calls, queueing and tool execution, charging failures/timeouts if they occur; none occurred here. Preparation, model startup, inter-wave time and the coach's model/tool time are outside this denominator. Foreground is timed separately and can finish after the last worker. Hourly rates extrapolate these short fixture waves.

The token rate includes **both background and foreground calls**, from the first model send to the final model response. Sum server-native completion tokens across calls before dividing by elapsed wall time, then take the median of three waves. The typical prompt was about 2.5K tokens and median output length 33. These short, natural tool turns spend time processing prompts and executing tools; the 256-token capped short-prompt benchmarks measure a different workload. Generated output text and lengths were allowed to vary; semantic task outcomes were checked.

The middle block reversed order and the final block rotated it. Foreground checked-result ranges were 8.32–12.67 s for regular eight, 6.30–12.08 s for coalesced eight, 10.20–12.57 s for coalesced fifteen, 12.47–13.07 s for regular sixteen and 11.37–12.54 s for coalesced sixteen. Three observations do not establish a stable tail percentile.

Hermes selected coalesced sixteen for highest rate and under a predeclared **completion-time** screen of no more than 20% above regular-eight median. That screen allowed 14.34 s and did not bound time to first usable output. For a person waiting for the next tool call, the eight-job arm had lower measured latency. No foreground request was marked or deliberately held for batching.

## Earlier C8 pilot

Three pairs ran eight background jobs plus a foreground probe. All 48 worker and six foreground attempts passed. Median worker rate was 3,536 regular versus 3,733 coalesced (+5.6%), with coalescing faster in two pairs and slower in one. Median first foreground tool time was 4.86 versus 4.00 s. All 27 paired sessions matched streamed text, semantic tool arguments, outcomes and finish reasons; two intermediate responses reported different native output counts. Prompt bodies matched after normalizing the isolated fixture directory paths that Hermes embedded. Unlike the later comparison, each wave had only eight total background jobs, without a backlog to refill.

## Resume after idle

Hermes resumed an existing tool conversation after 20 seconds idle and verified its saved state. Two paired tests kept the session's cache namespace or rotated it at resume; the model stayed loaded in both. All four resumed attempts passed.

| Resume condition | Cached native prompt tokens | Median next usable tool | Median checked result |
|---|---:|---:|---:|
| Fresh namespace | 0 / 5,478 and 0 / 5,481 | 1.41 s | 1.71 s |
| Same session namespace | 5,120 / 5,478 and 5,120 / 5,481 | **0.36 s** | **0.66 s** |

Both resumed requests matched after normalizing fixture paths, generated call IDs and cache namespace. Keep the serving process loaded, store each conversation outside GPU memory, and maintain a stable prompt prefix and private per-session namespace while appending tool results. Normal session traffic can reuse cached context; periodic model keepalive prompts are unnecessary for model residency. Cached prefixes can be evicted, and restarting loses this in-memory cache. The saved transcript permits reconstruction with another prefill. Longer idle periods, memory pressure and restart recovery are not established by this small screen.

## Evidence and limits

- [15 measured fleet waves](../results/hermes-fleet-waves.csv), [four resume attempts](../results/hermes-context-resume.csv), [sanitized observations](../results/vllm-followup-observations.json.gz) and [recomputed summary](../results/vllm-followup-summary.json).
- [Source, image and argument identities](../config/vllm-followup-identities.json), [experimental patch notes](ADMISSION_PATCH.md) and [private-source audit projections](../results/vllm-followup-audits.json). The runtime is the site's staged tree, not an exact frozen 1030 rebuild.
- Run `python3 tools/check_followup.py` to reproduce the arithmetic, task denominators and checked-state records offline. Raw streams, host traces, credentials, addresses and operator sessions remain private.

The fleet test observed no competing compute processes or logged compilation during timing, minimum guarded available RAM 40.83 GiB, and peak sampled GPU temperature 62 °C. No model, Engram, KV, clock, kernel, module or fabric changes were made between arms. All eight ranks returned to idle and the exclusive lease was released. No permanent serving route or agent configuration was installed. These synthetic tool tasks do not establish production coding quality, sustained throughput, or universal optimal worker counts.
