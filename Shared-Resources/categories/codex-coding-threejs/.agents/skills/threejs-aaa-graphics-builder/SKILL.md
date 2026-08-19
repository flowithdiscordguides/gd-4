---
name: threejs-aaa-graphics-builder
description: >-
  Upgrade Three.js scenes with authored forms, coherent art direction, materials, lighting, shaders, VFX, world kits,
  LOD, instancing, and performance-aware rendering without requiring an external generator.
---

# Three.js AAA Graphics Builder

## Governance and Scope

Apply repository governing instructions first. Resolve every reference from `references/` beside this file and every
sibling from `../<skill-name>/SKILL.md`; never search user-global skill directories. This skill never installs,
executes, builds, tests, launches, opens a browser, drives Playwright, probes credentials, calls providers, uploads,
downloads, uses credits, or accesses a network.

Use this skill when forms are primitive, the world is sparse, the material and lighting language is incoherent, VFX
obscures gameplay, or the user asks for premium, high-fidelity, showcase, or less-basic graphics.

## Reference Gate

For broad premium work, the phrase **core five references** means exactly:

1. `references/visual-scorecard.md`
2. `references/implementation-blueprint.md`
3. `references/model-recipes.md`
4. `references/render-recipes.md`
5. `references/technical-art.md`

Load every applicable core reference before editing its surface. Additionally load `references/shader-cookbook.md`
before shader, `onBeforeCompile`, sky, or post-processing work. Load the applicable checklist under
`references/checklists/` before assessing that category. Load `references/prompt-templates.md` only when the user asks
for a reusable prompt or task template. Record exact local paths and unavailable references honestly.

## Art Direction and Asset Strategy

Before implementation, create three genuinely distinct visual concepts. Vary composition, silhouette language,
materials, color energy, lighting, VFX behavior, and asset strategy. At least one concept must be non-obvious but
usable. Select one direction with a written rationale covering product fit, gameplay readability, memorability,
accessibility, responsive behavior, and implementation feasibility. Define its product-specific visual thesis and
signature moment.

Choose each surface from the smallest effective source:

- Existing repository assets when they fit the art direction and license constraints.
- Authored Three.js geometry, textures, materials, shaders, or VFX when browser-native construction is appropriate.
- User-supplied models, images, or audio after validating their runtime budgets and integration contracts.
- An optional external workflow only when the user explicitly authorizes the provider, exact inputs, credential use,
  expected outputs, and possible credit use.

External generation is never mandatory to claim high visual quality. Do not load generator skills merely to justify a
skip. If the user requests provider guidance, prepare a user-run plan; never call the provider or handle credentials.

## Workflow

1. Inspect current scene construction, camera, renderer, assets, materials, lighting, post-processing, VFX, UI
   relationship, responsive behavior, and technical-art constraints from source.
2. Score only what the available evidence supports across art direction, hero surface, obstacles, rewards, world,
   materials, render, VFX, UI cohesion, and performance architecture.
3. Establish reusable material, model-factory, world-kit, VFX, render-pipeline, and diagnostics boundaries only where
   the current architecture needs them.
4. Upgrade authored silhouettes and spatial composition before adding material detail, lighting, or effects.
5. Tie VFX to gameplay events and preserve threat, objective, reward, HUD, and focus readability.
6. Define budgets for draw calls, triangles, materials, textures, lights, shadows, particles, DPR, and post effects.
7. Add LOD, instancing, shared resources, culling, texture discipline, and disposal ownership where source evidence
   shows they are needed.
8. Re-score against `references/visual-scorecard.md` and distinguish source-backed rows from user-supplied runtime
   evidence.

## Core Rule

Glow does not make primitives premium. Build authored forms first, then materials, lighting, atmosphere, and effects.
Every dramatic choice must strengthen mood, hierarchy, orientation, feedback, or comprehension.

## Verification and Report

Re-read every changed source file and trace asset ownership, renderer setup, material reuse, disposal, resize, reduced
motion, responsive fit, and budget controls. Runtime appearance, screenshots, canvas pixels, frame rate, GPU cost,
console state, and provider outputs count only when supplied by the user. Otherwise mark them not runtime-verified and
do not claim visual or performance success.

Report the reference ledger, concept comparison, selected thesis and signature moment, asset-source decisions,
technical-art budget, scorecard, surfaces changed, source-level evidence, user-supplied evidence, accessibility and
readability safeguards, and remaining verification limits.
