# DeepSeek-V4.1-Flash-1017 on 8× DGX Spark: concurrency 1–8, cold prompts 2K–200K, code/prose results

Sharing a six-hour study of the official checkpoint on **SGLang TP8/EP8 + RoCEnante + DSPARK**, over 200GbE RoCE. One shared model service; 1M configured context, 6.6M shared FP8 E4M3 KV token slots. Full 1M quality was not tested.

**972 protocol-qualified requests with zero recorded request errors**: 756 main-matrix, 126 foreground-load and 90 separately validated corrective-soak requests. An additional 17 pilots and 96 original unqualified-soak requests are retained but excluded. The main matrix spans six input sizes, concurrency 1/2/4/6/8, code/prose, three repetitions, with 1,024-token capped outputs after synthetic reference notes. Generated code was not graded.

## Selected results

| Input/request | Workload | C | Decode tok/s/request | Actual batch output tok/s |
|---:|---|---:|---:|---:|
| 2,048 | code | 1 | 99.85 | 91.45 |
| 2,048 | code | 8 | 41.34 | 286.97 |
| 2,048 | prose | 1 | 53.84 | 52.02 |
| 2,048 | prose | 8 | 23.84 | 174.95 |
| 100,000 | code | 4 | 54.16 | 34.02 |
| 100,000 | code | 8 | 38.09 | 36.05 |
| 200,000 | code | 2 | 72.41 | 15.96 |
| 200,000 | code | 8 | 36.52 | 16.82 |

Decode is a middle-of-response window; actual batch output throughput includes prefill and queuing. They are not interchangeable. At 100K coding context, doubling four to eight requests increases whole-batch throughput only **6.0%** while worsening latency.

## Foreground interference matters

A short 2K-input/128-output foreground probe arrives 0.5s after background requests. Median first-token delay:

| Background requests | 8K input each | 100K input each |
|---:|---:|---:|
| 0 | 0.53 s | 0.52 s |
| 1 | 1.81 s | 25.30 s |
| 3 | 5.39 s | 76.25 s |
| 7 | 12.48 s | 176.54 s |

There are only three foreground samples per condition. Even one long cold prefill can hurt responsiveness; leaving an admission slot free does not solve it. Long concurrent prefills also caused multi-second/minute delivery stalls, so a fast later decode window is not a smooth-streaming guarantee.

**Original soak: unqualified protocol deviation.** Its 96 requests were code-only, not a code/prose mix. The study client peak was eight, but the backend reported nine requests in 182 of 1,863 samples. That attempt is retained and excluded from the primary qualified-request count; root cause is not established. The corrective attempt is a separate campaign, not an overwritten or silently pooled retry.

**Corrective soak: qualified under a changed admission policy.** A separate 900s admission window completed 90 requests (46 code / 44 prose), with both workloads at all four input lengths, no request errors, cache reuse or retractions. Client peak was eight and backend peak was eight across 1,818 samples, with no unknown probes or observed envelope excess. The final drain made the span 914.40s. It uses backend-aware paced admission (at least 0.25s between new reservations), so this is a bounded stability observation, not a peak-throughput comparison with the original soak or a guarantee of low interactive latency.

My takeaway: six to eight can help short-prompt offline batches, but long cold inputs need lower/admission-aware concurrency. The server's 32-request ceiling is not a worker target. No operating caps were changed.

Native counts, payload hashes and all 1,085 retained responses including excluded attempts were replay-checked; no nonzero cached-token counts were observed. Full tables, methods and charts are in the companion report draft. No apples-to-apples TensorFold/vLLM speedup is claimed. Credit to DeepSeek, SGLang, RoCEnante, DSPARK and Hermes contributors.
