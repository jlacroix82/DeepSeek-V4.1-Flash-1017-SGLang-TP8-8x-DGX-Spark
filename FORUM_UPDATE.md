Small follow-up: I have now tested atomic admission at **C16** on the same official 1017 checkpoint, with disk Engram, 10.5 GiB KV per rank and the 2 GHz cap unchanged.

| C16, all requests released together | Code tok/s | Prose tok/s |
|---|---:|---:|
| Regular admission | 598.7 | 564.6 |
| Atomic admission | **728.3** | **689.0** |

Those are paired, same-boot medians over ten waves per cell. Code 8+8 was slightly higher at **730.1 tok/s**. All **1,280 timed outputs** matched the reference text and token IDs, and every atomic wave formed the intended groups. We are still below Chris's published C16 means of about 805/754.

I also tested the normal streaming API with Hermes: all **240 background jobs and 15 foreground jobs** passed their tool/state checks. Sixteen active coalesced workers gave 11% more checked-job throughput than regular dispatch at sixteen; eight coalesced workers reached the first usable foreground tool call faster (3.52 s versus 7.65 s). These were short synthetic tool tasks, not a completed coding benchmark.

[Updated results, per-wave data, experimental patches and offline checker](https://github.com/jlacroix82/DeepSeek-V4.1-Flash-1017-SGLang-TP8-8x-DGX-Spark)
