---
name: threejs-game-director
description: >-
  Direct complete Three.js game work through the smallest authorized repository-local skill set. Use for new games,
  broad upgrades, premium visual passes, gameplay, UI, debugging, profiling, QA, and release preparation.
---

# Three.js Game Director

## Governance and Local Routing

Apply the repository's governing instructions before this skill. Read this skill's references only from
`references/` beside this file and sibling skills only from `../<skill-name>/SKILL.md`. Never search user-global skill
directories, source shell profiles, inspect credentials, or treat an unavailable sibling as permission to leave the
repository.

Select the smallest supporting set that covers the request:

- `threejs-gameplay-systems` for game design, playable loops, input, camera, collision, state, and game feel.
- `threejs-aaa-graphics-builder` for authored forms, materials, lighting, shaders, VFX, and technical-art budgets.
- `threejs-game-ui-designer` for HUDs, menus, overlays, responsive fit, accessibility, and touch UI.
- `threejs-debug-profiler` for source-traced defects and evidence-led performance analysis.
- `threejs-qa-release` for source-level QA, release readiness, and user-supplied runtime evidence.
- `threejs-animation` for mixers, clips, skeletal animation, morph targets, and GLTF animation playback.
- Generator skills only when the user requests asset-generation guidance or explicitly supplies generated assets.

For broad work, load the applicable phase skills rather than every sibling automatically. For a narrow request, load
only the directly relevant skill. Keep the routing decision visible and explain why each loaded sibling is necessary.

Delegation is optional and may use only repository-approved, parent-scoped direct-child roles: `investigator`,
`architect`, `implementer`, and `reviewer`. Give each child exact scope, allowed files, evidence requirements, and write
ownership. Never create generic workers, allow descendants, or delegate overlapping writes.

## Non-Execution Boundary

This skill never installs dependencies, runs scripts, builds, tests, starts servers, opens browsers, drives
Playwright, probes credentials, calls providers, uploads inputs, downloads outputs, uses credits, or accesses a
network. Never infer permission from tool availability.

When a command would help the user verify or operate the project, derive it from canonical repository source and label
it `User-run command`; the user decides whether to execute it and may return the output as evidence. Never describe an
unexecuted command as run.

External 3D, image, or audio providers are optional. Before discussing a provider-specific workflow, obtain explicit
authorization for that provider, the exact input artifacts that may leave the repository, expected output location,
credential use, and possible credit or plan use. Even with authorization, this skill prepares a user-run workflow; it
does not call the provider.

## Planning and Phase Routing

Load `references/phase-playbook.md` from this skill directory for broad work or whenever its ledgers and completion
gates are relevant. At each phase, load only the repository-local references required by that phase skill.

1. Establish scope, player promise, constraints, existing architecture, and verification limits.
2. For broad gameplay work, define the design brief, core-loop contract, and level or encounter plan.
3. Route implementation through the smallest applicable phase set and preserve shared-system regression contracts.
4. For visual work, require three genuinely distinct concepts, including one non-obvious usable direction, then
   document the selected product-specific thesis, rationale, and signature moment.
5. Decide asset sourcing per surface: existing repository asset, authored procedural asset, user-supplied asset, or
   optional user-authorized external workflow. Provider output is never mandatory for a premium-quality claim.
6. Keep gameplay, graphics, UI, animation, diagnostics, accessibility, responsive behavior, and reduced motion
   coordinated through explicit state and ownership boundaries.
7. Verify the current source completely. Add runtime, visual, performance, or provider evidence only when the user
   supplies it.

## Quality Gates

Do not equate glow, primitive density, or generic stat cards with premium quality. Premium work needs authored forms,
coherent materials and lighting, legible gameplay, purposeful VFX, a product-specific interface, responsive behavior,
accessible states, reduced-motion behavior, and performance-aware architecture.

For premium visual work, use the repository-local scorecard at
`../threejs-aaa-graphics-builder/references/visual-scorecard.md`. Source inspection may establish implementation and
configuration facts, but it cannot prove rendered appearance, frame rate, browser behavior, audio quality, or
provider success. Mark those rows `not runtime-verified` unless the user supplies current evidence.

## Evidence and Final Report

Keep concise ledgers for loaded skills, loaded references, routed phases, and asset-source decisions. Record exact
repository paths and distinguish `loaded`, `implemented`, `source-verified`, `user-supplied`, and `not verified`.

Report the design brief and loop contract when applicable, files changed, controls, architecture decisions, quality
gates, accessibility and responsive considerations, asset decisions, source-level checks, user-supplied evidence,
and remaining risks. Never report a run URL, screenshot, metric, provider output, or successful command without
current user-supplied evidence.
