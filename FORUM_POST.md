# DeepSeek V4.1 Flash on 8× DGX Spark: TP8/EP8 concurrency results

Sharing results from our **SGLang TP8/EP8 + RoCEnante + DSPARK** setup over 200GbE RoCE. One shared service, configured for 1M context and 6.6M shared FP8 KV token slots; full-window quality was not tested.

We tested cold inputs from **2K–200K tokens**, **1–8 concurrent requests**, code/prose workloads and three repetitions.

**At 2K input, with a 1,024-token output cap:**

| Workload | Single-request decode tok/s | Eight-request batch output tok/s |
|---|---:|---:|
| Code | 99.85 | 286.97 |
| Prose | 53.84 | 174.95 |

Decode uses a middle-of-response window; batch throughput includes prefill/queuing, so these are different metrics.

**The tradeoff:** at 100K coding context, four → eight requests added only **6% batch throughput**, while median first-token delay rose **64 → 114 seconds**. Spare request slots do not prevent long-prefill interference.

**972 protocol-qualified observations, zero recorded request errors.** An earlier unqualified soak is retained and excluded. These are capped serving tests—not code-quality or completed-agent benchmarks. The measured deployment is validated; a fresh rebuild of the portable recipe is not yet GPU-qualified.

[Full recipe, profiles, 60-cell tables, charts and methodology](https://github.com/jlacroix82/DeepSeek-V4.1-Flash-1017-SGLang-TP8-8x-DGX-Spark).

Credit to DeepSeek, SGLang, RoCEnante, DSPARK and the upstream Spark contributors.
