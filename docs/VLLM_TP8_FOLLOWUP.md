# vLLM TP8 follow-up on eight DGX Sparks

**November 6, 2026.** On the same eight-node cluster and official DeepSeek-V4.1-Flash-1017 checkpoint, putting eight short requests into the scheduler together made the fast C8 result repeatable. On a site build derived from [Christopher Owen's `spark-ds41f` 1030 recipe](https://github.com/christopherowen/spark-ds41f), the experimental path reached **560.39 code / 501.39 prose tok/s** at the 2 GHz GPU cap. The regular packed API in the same boot reached **424.35 / 382.96 tok/s**. The [original SGLang study](METHODS.md) remains a separate benchmark.

## What changed

A packed HTTP request can contain several prompts, but the regular API submits them to the engine individually. The scheduler can begin processing a partial group while the remaining requests are still arriving. In an earlier C8 screen, the same two groups of four sent about 65 ms apart became `4+4` only four times in ten code waves. The other waves became `3+5`, `2+6`, or `1+7`.

The experimental path sends each packed group as one message. The scheduler thread registers the whole group before running another model step. We call this **atomic admission**. It controls when a group becomes available to the scheduler; the scheduler still decides how much to process in each step. In this short, idle-start C8 test, the requested groups fit in the existing budget.

## Paired C8 results

Each cell has ten waves per method. The legacy and atomic paths ran in one boot, with identical requests, release delays, and packed, non-streaming responses. The method order alternated and the workload order rotated. All rates are medians of aggregate native output tokens per second, measured from the first client send to the last completion, including the planned delay.

| Workload | Release pattern | Legacy tok/s | Atomic tok/s | Intended prompt groups formed, legacy → atomic |
|---|---|---:|---:|---:|
| Code | All eight together | 424.35 | **560.39** | 0/10 → 10/10 |
| Code | 4+4, 65 ms apart | 424.91 | **530.21** | 3/10 → 10/10 |
| Code | 1+7, 25 ms apart | 422.72 | 421.97 | 10/10 → 10/10 |
| Prose | All eight together | 382.96 | **501.39** | 2/10 → 10/10 |
| Prose | 4+4, 120 ms apart | 478.09 | **483.61** | 6/10 → 10/10 |
| Prose | 1+7, 25 ms apart | 380.85 | 382.05 | 10/10 → 10/10 |

The all-eight atomic waves ranged from **537.14–564.41 tok/s for code** and **488.35–505.01 for prose**. Both atomic code patterns beat the fastest code wave in [Chris's public switched TP8 receipt](https://github.com/christopherowen/spark-ds41f/blob/6c57fd2f/manifests/benchmarks/2026-10-30-spark-ds41f-1030-switched8.json), **472.88 tok/s**, in all ten repeats. Against that receipt's C8 averages, the all-eight medians were **18.9% above 471.33 for code** and **4.6% above 479.17 for prose**. The prose waves all stayed below his fastest prose wave of **533.14 tok/s**. These are cross-deployment reference figures; the paired legacy comparison measures the effect on this cluster.

The [120 timed waves](../results/vllm-atomic-c8.csv) retain the intended release groups, fresh prompt groups reconstructed from scheduler steps, elapsed time and token counts. Each wave produced 2,048 native tokens. All **960 timed responses** matched the text and token IDs in our local reference. The text hash prefixes also match Chris's published C8 records. The test held the checkpoint, disk-backed Engram, 10.5 GiB KV allocation per rank, worker images and 2 GHz GPU cap fixed. The candidate passed prompt rendering, protocol and thinking checks, plus a batch-specific test for response ordering and invalid-request rejection. A first candidate failed its response-assembly check and produced no timed results; the table uses the corrected candidate.

The short prompts are from [Chris's pinned benchmark client](https://github.com/christopherowen/spark-ds41f/blob/5f84eda602ace7ae97cd5d451f19ba8c0403f8ef/bin/spark#L3671-L3685): a Python LRU cache request (75 native input tokens) and an explanation of speculative decoding (68). Temperature was zero, seed 42, and the cap was 256 tokens per request. Both workloads reached the cap in reasoning output. These rates measure a packed batch finishing; they do not measure time to first streamed output, completed coding tasks or sustained serving under mixed load.

## Other results from the follow-up

- **Original 2K workload:** With 2,048 input tokens and 1,024 output tokens per request, a separate vLLM C8 screen averaged **361.54 code / 245.38 prose tok/s** over three waves. The historical SGLang medians were **286.97 / 174.95**. This compares two deployments with different serving and client settings. The 75/68-token C8 figures above belong to a different workload.
- **C16:** Changing client release timing alone gave little repeatable benefit. The best medians were **583.44 code / 558.11 prose tok/s**, versus **804.63 / 753.59** in Chris's published C16 summary. That summary does not contain raw C16 wave records. **Atomic admission has only been measured at C8.**
- **Engram:** In a separate warm test at 2 GiB KV per rank, device-resident Engram used about **24 GiB more memory per rank** and was **2.8% slower for code and 4.2% slower for prose at C16** than disk placement. Placement also changes how ranks combine table data. This result does not settle cold, long-context, or other Engram implementations.
- **Clocks and fabric:** A separate C8 clock comparison gained **1.35% for code and 4.31% for prose** at stock clocks on the short prompts. The atomic experiment used the restored 2 GHz cap. In a separate fabric replay, both configured RoCE paths carried traffic on all eight ranks. The counters did not establish fabric latency as a cause of the remaining C16 gap.

The follow-up covers short-batch throughput and exact output equivalence on these prompts. The atomic path has not been qualified for production deployment or as a replacement for the original SGLang recipe. No serving or host setup changes are part of this repository update.
