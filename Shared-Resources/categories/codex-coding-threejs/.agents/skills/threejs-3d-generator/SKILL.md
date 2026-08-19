---
name: threejs-3d-generator
description: >-
  Plan authorized, user-run 3D asset generation and integrate supplied GLB or FBX models into Three.js, including
  texturing, rigging, animation, conversion, budgets, loading, validation, and browser-safe asset ownership.
---

# Three.js 3D Generator

## Governance and Authorization

Apply repository governing instructions first. Read references only from `references/` beside this file and sibling
skills only from `../<skill-name>/SKILL.md`; never search user-global skill directories. This skill never probes
credentials, sources shell profiles, executes scripts, calls a provider, uploads an image or model, downloads output,
uses credits, installs, builds, tests, launches, opens a browser, or accesses a network.

External 3D generation is optional. Before preparing provider-specific guidance, require explicit user authorization
for the provider, exact input artifacts that may leave the repository, intended task, credential use, output
directory, retention expectations, and possible credit or plan use. Never inspect or report secret values. The user
owns every provider action and may return sanitized task metadata and local output paths as evidence.

## Reference Gate

- Load `references/api-notes.md` before describing provider parameters, task relationships, rigging, retargeting,
  post-processing, conversion, or output handling.
- Load `references/threejs-integration.md` before integrating a user-supplied GLB or FBX.
- Load `references/image-generator-workflows.md` before proposing a 2D-reference-to-3D workflow.

Record exact repository-local paths. If a reference is unavailable, limit the affected guidance instead of searching
outside the repository or inventing current provider behavior.

## Asset Brief

Define the asset's gameplay role, readable silhouette, scale, pivot, orientation, material zones, texture needs,
animation needs, collision proxy, LOD plan, target file type, triangle/material/texture budgets, and mobile tier before
any external workflow. For riggable characters, request one coherent full-body mesh in a clear T- or A-pose with
limbs separated and props detached. For creatures, align the authored stance with intended locomotion.

Use a strong 2D reference only when it materially improves silhouette, proportions, costume zones, or consistency.
Load `../threejs-image-generator/SKILL.md` only for a user-requested manual image workflow.

## User-Run Provider Plan

When authorization exists, provide a reviewable plan rather than taking provider action. Include:

1. Sanitized prompt and input list.
2. Provider operation sequence and task-ID relationships.
3. Requested output formats and browser budgets.
4. User-owned credential, upload, generation, status, and download steps.
5. Local destination paths inside the repository.
6. Validation criteria and what evidence the user should return.

Provider versions, presets, formats, quotas, and costs can change. Use only repository-local provider notes or current
user-supplied provider evidence; otherwise label the detail unverified.

## Rigging and Animation Contracts

- Validate a supplied skeleton's hierarchy, bone names, symmetry, chain depth, bind pose, skin weights, root motion,
  and clip track coverage before integration.
- A provider's `riggable` status is not proof of a usable rig. Visually warped or shallow limb chains require a new
  user-owned provider attempt or local asset correction, not code that hides the defect.
- Retarget operations must reference the rig result expected by the provider, not an unrelated generation task.
- Never recommend in-place baking when repository provider notes record corruption; preserve root motion and remove it
  deliberately during import when gameplay requires in-place locomotion.
- Inspect supplied clip names, durations, tracks, root transforms, scale tracks, and morph bindings before creating
  `AnimationAction` mappings.

## Three.js Integration

- Prefer GLB with PBR materials when it meets the source pipeline; use `GLTFLoader`. Use `FBXLoader` only when the
  supplied animation path requires FBX.
- Normalize scale, pivot, forward axis, bounds, shadow flags, material color space, and texture settings explicitly.
- Treat model files as repository assets. Never place provider credentials or provider calls in browser code.
- Use `AnimationMixer` for clip playback and keep mixer update, action transitions, root-motion handling, and cleanup
  owned by a dedicated animation system.
- Audit file size, triangles, draw calls, materials, textures, skeleton bones, morph targets, clips, LOD, collision,
  cloning strategy, and disposal before connecting the model to gameplay.

## Verification and Report

Source inspection can verify loader configuration, asset paths, budgets, action wiring, ownership, and cleanup.
Provider success, uploaded inputs, task status, downloaded files, rendered appearance, rig deformation, animation
quality, and performance require current user-supplied evidence. Mark them unverified otherwise.

Report authorization scope, local references, asset brief, user-run plan, sanitized user-supplied task metadata,
local output paths, integration decisions, budget audit, source-level checks, and remaining runtime/provider limits.
