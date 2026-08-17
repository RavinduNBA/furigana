# Phase 5 provider prompt review checklist

- [ ] Five prompt packets are byte-identical across runs and match the golden.
- [ ] Each prompt contains only its bounded request context and supplied records.
- [ ] Prompt hashes and provider cache keys are stable and provenance-sensitive.
- [ ] Strict response instructions preserve publisher and dictionary precedence.
- [ ] Fake-provider first runs miss the cache and second runs hit it.
- [ ] Refusal, malformed output, transport failure, and invalid schemas fall back.
- [ ] Failed responses are not cached and diagnostics contain only safe reason types.
- [ ] Prompts, reports, caches, and diagnostics contain no credentials or paths.
- [ ] Dictionary-only and local-scripted behavior remains unchanged.
- [ ] No test or regression command makes a network call.

Review record: pending.
