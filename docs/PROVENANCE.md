# Provenance and validation boundaries

## Evidence already established

The saved measurements came from a working retained eight-node SGLang TP8/EP8 deployment using the official DeepSeek-V4.1-Flash-1017 checkpoint, RoCEnante, DSPARK and FP8 E4M3 KV. The main and foreground results were independently recomputed. A separately identified, paced corrective soak qualified; the original unqualified soak remains disclosed. See METHODS.md and DEVIATIONS.md.

The measurement source/protocol hashes, effective settings and sanitized event-count export are in `../results/summary.json` and `../results/observations.json.gz`. Full raw token IDs/text, credentials, host topology and operational working directories are not redistributed. These exports support metric reproduction, not an identical-weight or clean-machine runtime-reproduction claim.

## Recipe source pins

- Source foundation: `MiaAI-Lab/DeepSeek-v4.1-Flash-DGX-Sparks`, commit `64b02dea8681fb1d8e3a659ea432a8e9e9ba3995`.
- Base image: `lmsysorg/sglang:dev-dsv41@sha256:3dbc313030a6ef2c5d7de8ecf48e9aece722694a82182cb618cc82b588816349`.
- Build file: `Dockerfile.canary-roce`, source SHA-256 `825a07a05b013ab2c15562d0a7c3fc7cc63df2c225464412384b37690d50597d`.
- Upstream SGLang source: `f80c91a4b97e52e17fbcff088aa6b47b6270f6b9`, with the upstream recipe's pinned overlays and package versions. Its `runtime/sources.manifest` covers fetched source archives and local patches.
- The recipe's suggested official model revision is `1bae0e1088993b9b82de08f59de5be5a34e42170`; this is an upstream preparation pin, not a freshly recomputed full checkpoint hash of the measured deployment.
- `patches/upstream-tp8-launcher.patch` preserves the measured launcher's small forwarding changes for RoCEnante and related toggles, plus named Dockerfile selection on the non-TP4 launcher path. It does not assert every untracked/local optimization is captured.

## Source-review follow-up

The upstream commit contains a node-count-generic launcher and transport code admitting world sizes4/8, but no tracked measured TP8/EP8 profile. This repository supplies its own review-stage profile. Upstream TP4-only hooks and transport tuning must not be assumed to match the retained measured images. The source audit did not inspect the measured checkpoint bytes: it does **not** establish either equality or a difference against the suggested upstream model revision.

`boot.py` explicitly forwards `EXTRA_SGLANG_ARGS`; it has no first-class fields for the saved KV dtype, page size and maximum prefill-token setting. The portable profile therefore now carries `--kv-cache-dtype fp8_e4m3 --page-size 256 --max-prefill-tokens 32768` explicitly through that path. These are configuration/forwarding checks, not a new native-serving qualification. DSPARK block size remains5; do not replace it with an independently interpreted speculative-token flag.

Use distinct TP8 Engram output directories and verify every rank's `of8` shards before deployment; do not mix existing TP4-packed artifacts. If using NFS, independently verify that the export/client list covers the seven intended workers. The public source's TP4 transport/performance measurements do not qualify a freshly rebuilt TP8/EP8 ring.

## What differs from a clean reproduction kit

The measured ring was restored from retained per-node containers and images. All eight image IDs differ and are recorded without private topology in `../config/measured-runtime.json`. A matching source commit, base image or launch profile alone cannot establish that a fresh build reproduces those image bytes, source overlays or performance. The newly rendered portable profile has not been loaded across a fresh eight-node ring.

| Gate | Scope/status |
|---|---|
| Saved benchmark records and raw native replay | Verified for measured retained runtime |
| Main/foreground independent arithmetic review | Verified |
| Corrective soak validation and operational return | Verified; distinct source/admission policy |
| Repository parsing/profile/source-prepare/dry-run checks | Record exact test output in release checks |
| Fresh ARM64 serving-image build from this port | NOT_RUN; no serving build authorized by repo setup |
| Fresh eight-node load, all-rank smoke and generation | NOT_RUN |
| Rebenchmark of newly built image/profile | NOT_RUN |
| Public GitHub visibility/forum announcement | Owner-authorized publication; verify the live repository/topic separately |

A fresh-build failure is not being hidden: these gates have not been attempted. A future qualification should bind exact image IDs, effective model/Engram/template inputs, request generator, all-rank health, tool behavior and performance to the new build before promotion.

## Attribution and licensing

This recipe patch derives from the upstream AGPL-3.0-or-later work. The complete AGPL licence is retained as `../LICENSE`, the original MIT skeleton notice as `../LICENSE.upstream-MIT`, SGLang's Apache terms as `../LICENSE.sglang`, and the component attribution as `../NOTICE.upstream`. Fetched runtime components and model weights retain their own terms. No model weights are redistributed. This repository does not claim authorship of the upstream inference engines or a new quantization.
