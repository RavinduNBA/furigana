# Phase 5 provider prompt review checklist

- [x] Five prompt packets are byte-identical across runs and match the golden.
- [x] Each prompt contains only its bounded request context and supplied records.
- [x] Prompt hashes and provider cache keys are stable and provenance-sensitive.
- [x] Strict response instructions preserve publisher and dictionary precedence.
- [x] Fake-provider first runs miss the cache and second runs hit it.
- [x] Refusal, malformed output, transport failure, and invalid schemas fall back.
- [x] Failed responses are not cached and diagnostics contain only safe reason types.
- [x] Prompts, reports, caches, and diagnostics contain no credentials or paths.
- [x] Dictionary-only and local-scripted behavior remains unchanged.
- [x] No test or regression command makes a network call.

Review record: PASS on 2026-08-17 at commit `fddc4dd`, reviewed by Ravindu.
Machine verification passed prompt identity, bounded context, strict schemas,
cache miss/hit behavior, safe fallback, and credential/path exclusion. Manual
review passed 言葉 prompt sufficiency, 表舞台 publisher-reading precedence,
雪乃 name separation, 振り返る sense constraints, and the shared response
contract. Retained fake-provider artifacts record zero network calls; this is
artifact evidence and does not claim observation of external network state.
