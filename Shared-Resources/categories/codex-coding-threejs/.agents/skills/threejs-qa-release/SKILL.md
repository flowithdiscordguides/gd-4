---
name: threejs-qa-release
description: >-
  Audit Three.js game and release readiness through source-level QA, user-supplied playtest and visual evidence,
  responsive checks, hosting configuration, debug gating, asset budgets, and explicit release risks.
---

# Three.js QA Release

## Governance and Local References

Apply repository governing instructions first. Read references only from `references/` beside this file and sibling
skills only from `../<skill-name>/SKILL.md`; never search user-global skill directories. This skill never installs,
builds, tests, starts a server, previews, opens a browser, drives Playwright, runs a bot, executes an inspector, probes
credentials, calls providers, uploads, downloads, or accesses a network.

Load `references/qa-release-checklists.md` for broad QA or release work. Load the applicable files from
`references/checklists/`: `visual-verification.md`, `playtest-qa.md`, `release.md`, `visual-test-harness.md`, and
`bot-playtest.md`. Load `references/visual-test-harness.md` when baseline design is in scope and
`references/playtest-bot.md` when scripted-playtest architecture is in scope. Load `references/prompt-templates.md`
only when the user requests a reusable prompt or task template.

## Source-Level QA Workflow

1. Trace canonical scripts without running them, entrypoints, environment needs, Vite or hosting base paths, public
   assets, loaders, fallback states, error handling, debug gates, test hooks, and production configuration.
2. Build a matrix for boot, loading, active play, pause, settings, objective progress, fail/retry, win or milestone,
   resize, narrow and short viewports, touch input, keyboard input, reduced motion, audio unlock, and cleanup.
3. Trace the main input-to-objective and fail-to-retry paths end to end in source.
4. Audit HUD text constraints, safe areas, touch targets, focus behavior, state feedback, and world visibility.
5. Review asset URLs, file-size declarations when available, texture and model ownership, bundle registration,
   disposal, and likely static-hosting failures.
6. Decide whether a visual harness and bot-playtest design should be added, extended, or skipped. State the evidence
   and determinism constraints; never claim either was executed.
7. Gate debug UI, logs, diagnostics, test hooks, source maps, and development-only controls according to the current
   release contract.

## Runtime Evidence Boundary

Screenshots, canvas pixels, console and network logs, browser/device behavior, frame metrics, audio playback, build
output, preview behavior, bot metrics, and deployment results count only when the user supplies current evidence.
Never infer them from source or fabricate pass/fail rows.

When canonical repository commands would collect missing evidence, list them as `User-run command` templates with the
working directory, expected artifact, and interpretation. The user owns dependency installation, builds, tests,
servers, browsers, inspectors, Playwright, and deployment.

## Release Decision and Report

Use `PASS` only for claims fully supported by source plus any necessary user-supplied runtime evidence. Use
`SOURCE-READY / RUNTIME UNVERIFIED` when static checks pass but execution evidence is absent. Use `BLOCKED` when a
known defect or unmet prerequisite prevents release.

Report the local reference ledger, QA matrix, source trace, visual-harness and bot-playtest decisions, canonical
user-run commands, user-supplied artifacts, hosting assumptions, debug gating, source-level findings, runtime limits,
known issues, and residual release risks. Never report an unobserved URL, screenshot, metric, build, or deployment.
