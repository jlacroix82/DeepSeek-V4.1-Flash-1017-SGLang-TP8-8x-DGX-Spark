# Initial private-repository validation

These checks were actually exercised during repository setup. They are not a substitute for a fresh serving qualification.

## Passed

- `python3 -m unittest discover -s tests`: **37 CPU tests passed**, including command-injection/inline-secret rejection, request-profile construction, ownership/directory guards, execution acknowledgement, real CLI entry points and an intentionally tampered-results negative control.
- `python3 tools/check_results.py`: independently recomputed all **60 main-matrix cells /180 waves** from sanitized native event-count records. Checked1,085 retained request records,972 protocol-qualified requests and the separate96-request exclusion; zero recorded request errors.
- Real source-only `prepare --directory .runtime/upstream`: fetched public upstream commit `64b02dea8681fb1d8e3a659ea432a8e9e9ba3995`, applied the TP8 launcher patch and verified the Dockerfile SHA-256 `825a07a05b013ab2c15562d0a7c3fc7cc63df2c225464412384b37690d50597d`.
- Actual render into that prepared checkout using a deliberately nonproduction fixture; profile/wrapper emitted and `bash -n` passed for the wrapper, generated environment and patched upstream launcher.
- Actual `run doctor` default dry-run performed no command and wrote no files. `--execute` alone was refused; both explicit execution/qualification flags are required.
- All original results-file bytes preserved. Relative Markdown links resolve, chart SVG XML parses and no SVG script elements were present.
- AGPL/MIT/Apache and component notices retained. Local Git author uses the owner's GitHub noreply address, not a personal email.

The public source/configuration and fixture check did not download weights, build a serving image, SSH to worker hosts, allocate GPUs or restart production. The measured ring was not redeployed.

## Intentionally NOT_RUN

- Fresh ARM64/CUDA serving-image build and verification of byte-equivalence to retained measured images.
- New eight-node model load, native/API/tool qualification and rebenchmark on that rebuilt image.
- Auth/proxy provisioning for another operator's network.
- Public repository promotion or a forum post.

GitHub Actions runs the CPU/metric/example-plan/checksum checks. Its remote run status is separate from the local results above and should be checked before review/promotion. Full binary/runtime equivalence remains explicitly unestablished; see PROVENANCE.md.
