# Scope and safe handling

This is a private review-stage recipe/results repository. Do not change visibility or post the forum draft until its owner approves publication.

- Never commit actual host addresses, user home paths, API keys, access tokens, SSH keys, passwords, raw private Docker inspect output or protected environment files.
- Use the documented example configuration and keep edited local profiles ignored by Git. The recipe helper refuses inline secret values; it does not provision endpoint authentication.
- Treat upstream build/share/pack/serve/stop actions as potentially disruptive. Plan is local-only, `run` defaults to dry-run, and real execution requires explicit switches. Do not use them against the measured production deployment as part of a GitHub/CI check.
- Source fetch/patch and CPU tests do not qualify a new runtime image. Never expose an unauthenticated model endpoint or advertise a clean rebuild as having the saved benchmark rates.
- Keep sensitive findings in an appropriate private channel. Do not attach credentials or raw private logs to public issues.

No cloud model, model-weight download, serving-image build or GPU execution is required by this repository's CI. The source checkout created by `prepare` belongs under an ignored local path and is not a submodule whose private contents should be uploaded.
