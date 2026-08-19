---
name: threejs-game-ui-designer
description: >-
  Design expressive, accessible Three.js HUDs, menus, overlays, settings, touch controls, responsive layouts, safe
  areas, typography, and UI-to-world cohesion.
---

# Three.js Game UI Designer

## Governance and Local References

Apply repository governing instructions and UI/UX standards first. Read references only from `references/` beside
this file and siblings only from `../<skill-name>/SKILL.md`; never search user-global skill directories. This skill
never installs, builds, tests, starts a server, opens a browser, runs Playwright, probes credentials, calls a provider,
uploads, downloads, uses credits, or accesses a network.

Load `references/ui-patterns.md` for HUD, menu, overlay, settings, touch, typography, responsive, safe-area, icon, or
UI/world-cohesion work. Load `references/checklists/game-ui-quality.md`,
`references/checklists/hud-readability.md`, and `references/checklists/responsive-ui-fit.md` before assessing those
categories. Load `references/checklists/mobile-input.md` for touch controls or mobile safe areas. Load
`references/prompt-templates.md` only when the user requests a reusable prompt or task template.

## Required Concept Selection

Before styling or layout implementation, define the product surface, player context, gameplay priorities, input
methods, responsive targets, accessibility needs, and existing design system. Then produce three genuinely distinct
concepts that vary in composition, typography, color or material language, signature interaction, and asset strategy.
At least one concept must challenge the obvious HUD or menu pattern while remaining usable.

Compare all three for product fit, gameplay readability, memorability, accessibility, responsive fit, reduced-motion
behavior, and implementation feasibility. Document the selected concept and why it is stronger than the rejected
directions. State a product-specific visual thesis and one signature moment that reinforces the game's identity or
feedback rather than adding unrelated decoration.

## Workflow

1. Trace actual game state, UI projection, input intents, current components, tokens, icon system, and screen states.
2. Inventory gameplay, loading, empty, pause, settings, fail/retry, win or milestone, error, and touch states.
3. Prioritize survival or status, objective, immediate feedback, and flavor; keep one obvious next action per state.
4. Replace generic dashboard cards with genre-specific meters, clusters, badges, alerts, diegetic cues, or focused
   modal compositions only when those patterns improve comprehension.
5. Use stable dimensions, safe-area insets, realistic text-fit constraints, localized-content tolerance, and
   intentional z-order that preserves player, threat, reward, and reticle visibility.
6. Implement accessible names, keyboard focus where supported, sufficient contrast, non-color state cues, touch
   targets, and hover, pressed, selected, disabled, loading, error, and destructive states.
7. Respect `prefers-reduced-motion` and provide a usable low-motion form of the signature interaction.
8. Wire controls to normalized gameplay intents and render UI from authoritative game state rather than duplicated
   rules.
9. Treat external images or 3D assets as optional. If the user requests provider guidance, require explicit provider,
   upload, credential, output, and credit authorization, then prepare only a user-run workflow.

## Verification and Report

Re-read every changed source file and audit hierarchy, state coverage, stable sizing, text-fit rules, safe areas,
z-index, pointer behavior, keyboard semantics, touch intents, responsive breakpoints, and reduced-motion branches.
Rendered appearance, overlap at runtime, screenshots, touch behavior, and real state transitions require current
user-supplied evidence. Otherwise report source-level verification and mark runtime visual behavior unverified.

Report the local reference ledger, three concepts, selection rationale, visual thesis, signature moment, UI state
matrix, controls, accessibility, responsive and reduced-motion decisions, files changed, source evidence,
user-supplied evidence, and remaining risks.
