---
name: threejs-gameplay-systems
description: >-
  Design and implement Three.js game loops, mechanics, entities, input, camera, collision, objectives, encounters,
  difficulty, feedback, audio hooks, and maintainable update architecture.
---

# Three.js Gameplay Systems

## Governance and Scope

Apply repository governing instructions first. Read references only from `references/` beside this file and siblings
only from `../<skill-name>/SKILL.md`; never search user-global skill directories. This skill never installs, runs a
scaffold, builds, tests, starts a server, opens a browser, uses Playwright, accesses a network, or calls a provider.

Use for new playable slices, mechanics, entity systems, input, camera, collision or physics, rules, scoring,
objectives, levels, arenas, tracks, waves, puzzles, combat, progression, difficulty, restart loops, and game feel.

## Reference Gate

- Load `references/gameplay-workflows.md` for architecture, mechanics, entities, input, camera, scoring, feedback, or
  first-playable work.
- Load `references/game-design-level-design.md` for broad creation, major gameplay changes, levels, encounters,
  progression, difficulty, or polished-gameplay claims.
- Load `references/physics-engine-selection.md` before physics, collision-heavy movement, vehicles, rolling bodies,
  sensors, projectiles, platforms, or character-controller changes.
- Load `references/game-feel.md` before movement, camera feel, hitstop, screenshake, impact, easing, or juice work.
- Load the applicable checklist under `references/checklists/` before assessing its category.
- Load `references/prompt-templates.md` only when the user requests a reusable prompt or task template.

Record each selected repository-local reference and any read failure. An unavailable reference limits the affected
claim; it does not authorize a global search or an invented fallback.

## Workflow

1. Trace current manifests, entrypoints, update loop, state ownership, input, camera, entities, collisions, UI events,
   audio events, diagnostics, and categorical neighbors.
2. Write a compact design brief: player promise, target feeling, primary verb, objective, pressure, reward, fail or
   retry, skill expression, and non-goals.
3. Define the core-loop contract: input verb, state transition, objective progress, pressure, reward, and restart.
4. Define the level or encounter plan: opening, first decision, first threat, first reward, landmarks, escalation,
   recovery, readability, failure conditions, and tuning knobs.
5. Preserve explicit ownership and update order across input, simulation, collision, animation, camera, VFX, audio
   events, UI projection, and rendering.
6. Choose collision or physics from actual mechanics and determinism needs. Keep fixed-step simulation separate from
   frame rendering when required.
7. Implement the smallest complete playable increment, including feedback, state-driven HUD or audio hooks,
   fail/retry behavior, cleanup, and diagnostics.
8. Keep hot paths allocation-light, dispose resources deliberately, and avoid abstractions without a second consumer.
9. Source-verify every reachable input and state transition against the current code.

## Integration Rules

- Gameplay owns rules; UI, audio, animation, and VFX consume explicit state or events rather than duplicating rules.
- Input adapters emit normalized intents and do not directly mutate unrelated systems.
- Camera motion preserves the next decision and respects reduced-motion settings for shake or aggressive FOV changes.
- Imported or generated assets remain optional. Load `threejs-audio-generator` only when the user requests a manual
  asset workflow; gameplay can still define provider-neutral audio events and runtime contracts.
- Dependencies may be proposed only from canonical project needs. The user owns every install command.

## Verification and Report

Re-read all changed files and trace the main input, objective, reward, fail, and retry paths. Source inspection can
verify registrations, ownership, update order, cleanup, and expected transitions. Playability, timing feel, browser
behavior, collision outcomes, screenshots, canvas pixels, console state, and audio playback require current
user-supplied evidence. Mark them not runtime-verified otherwise.

Report the reference ledger, design brief, core-loop contract, level or encounter plan, architecture decisions,
controls, tuned constants, files changed, source-level checks, user-supplied evidence, and remaining edge cases.
