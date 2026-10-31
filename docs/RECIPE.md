# TP8 recipe and operator sequence

## Status: review-stage portable port

The benchmark results describe the retained, working eight-node deployment. This repository also provides a pinned-source preparation/configuration recipe. **A fresh build and new eight-node deployment of this portable port have not been qualified.** Do not attribute the saved benchmark numbers to a newly built image merely because its flags match.

The source foundation is MiaAI-Lab's DeepSeek-V4.1-Flash-DGX-Sparks at `64b02dea8681fb1d8e3a659ea432a8e9e9ba3995`, with the measured TP8 launcher's small environment-forwarding/build-selection patch. Its pinned `Dockerfile.canary-roce` builds the SGLang/RoCEnante runtime. The pin, base image digest and suggested model revision are in `config/recipe.lock.json`. The model revision is the source recipe's pin; it is not a newly computed complete weight-file digest of the measured deployment.

## Prerequisites

- Eight DGX Spark/GB10 hosts with an operator-validated 200GbE RoCE fabric. Record the correct socket interfaces, HCA names and GID indices for your own installation. This recipe does not configure switches, addresses, drivers or kernel policy.
- Working Docker/NVIDIA Container Toolkit on every node and passwordless SSH to the seven worker aliases. Run the upstream orchestrator from the head/rank0 host; the head alias in the example is descriptive, not an automatic SSH jump.
- Enough local NVMe storage for the official model and prepared Engram shards. Review the upstream checkpoint preparation and NFS layout before serving. No weights are included or downloaded by the helper.
- Python3.10+ and Git for the CPU-only recipe helper. The serving image's Python/CUDA packages come from its separate pinned upstream build, not a local pip install in this repository.
- A backup/rollback plan and an explicit maintenance window before touching an existing serving ring. Read and preserve upstream licence/model terms.

## 1. Inspect a safe plan

```bash
cp config/tp8.env.example .env.tp8
python3 tools/recipe.py plan --env-file .env.tp8
```

The example uses reserved documentation addresses and `example.invalid` aliases. Replace all example/SET/replace fields before rendering or execution. `plan` is local and does not SSH, allocate a GPU or start a container. The helper parses values without shell evaluation; it rejects inline API keys, tokens, command substitutions and backticks.

## 2. Prepare the pinned upstream source only

```bash
python3 tools/recipe.py prepare --directory .runtime/upstream
```

This fetches a Git source revision and applies the explicit TP8 launcher patch. It does **not** download model weights, build the runtime, configure NFS or start a model. The checkout is intentionally ignored by this report repository's Git history. Refuse an unexpected existing checkout rather than overwrite somebody else's work.

## 3. Render the edited eight-node profile

After editing the example into a real local configuration:

```bash
python3 tools/recipe.py render --env-file .env.tp8 --runtime .runtime/upstream
```

This writes the upstream checkout's separate `.env.tp8` profile and `start-tp8.sh` wrapper. The wrapper does not select the TP4 launch path. It keeps TP4/TP3 state directories distinct. Rendering is not deployment.

High-level measured settings include TP8/EP8,1,048,576 context,6,600,000 configured token pool,32 running-request limit,4,096 prefill chunk,0.90 static memory fraction, DSPARK block size5 (six native configured speculative tokens), RoCEnante enabled and GPU Engram cache size0. These are observed settings, **not universal memory-safety defaults**. The additional effective shared numeric container flags are retained in `config/measured-runtime.json`; not all are automatically forwarded by the portable launcher.

## 4. Review the upstream actions without executing them

```bash
python3 tools/recipe.py run doctor --env-file .env.tp8 --runtime .runtime/upstream
python3 tools/recipe.py run build --env-file .env.tp8 --runtime .runtime/upstream
python3 tools/recipe.py run share --env-file .env.tp8 --runtime .runtime/upstream
python3 tools/recipe.py run pack --env-file .env.tp8 --runtime .runtime/upstream
python3 tools/recipe.py run serve --env-file .env.tp8 --runtime .runtime/upstream
python3 tools/recipe.py run smoke --env-file .env.tp8 --runtime .runtime/upstream
```

These `run` invocations default to **DRY RUN**. They show the intended command; they do not perform it. Real invocation requires both `--execute` and `--ack-unqualified-port`, a deliberately explicit acknowledgement that this portable port needs independent deployment qualification. Do not enable those switches on a production ring on the strength of the saved measurements.

The upstream sequence and prerequisites remain operator responsibilities: doctor → image build/distribution → checkpoint availability → NFS share → correct per-rank Engram preparation → serve → all-rank smoke and authenticated completions. `build`, `share`, `pack`, `serve` and `stop` can change remote hosts, consume substantial resources or interrupt serving. `stop` is not an automatic rollback plan.

## Authentication and exposure

Do not expose an unauthenticated API. This helper deliberately refuses nonempty inline secret variables, and is **not** an authentication/proxy provisioning tool. Review the upstream runtime's credential handling and supply an appropriate private network/TLS/authenticated gateway before enabling real serve. No credential, private key or token belongs in a committed env file. The empty API_KEY example is not a recommendation to serve publicly without authentication.

## Verification boundaries

Local tests establish parsing, profile construction, source pin/patch handling and dry-run safety. A prepared checkout or CPU test does not establish an ARM64 image build, CUDA correctness, runtime-source equivalence or fresh serving performance. The measured ring used retained images whose IDs differ across the eight nodes. See `PROVENANCE.md` before claiming clean reproduction. This is the remaining gate before a public deployment-kit claim.
