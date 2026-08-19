---
name: threejs-debug-profiler
description: >-
  Diagnose Three.js rendering, loading, animation, resize, input, collision, and performance problems through complete
  source tracing and clearly separated user-supplied runtime evidence.
---

# Three.js Debug Profiler

## Governance and Local References

Apply repository governing instructions first. Read references only from `references/` beside this file; never search
user-global skill directories. This skill never installs, executes, builds, tests, starts a server, opens a browser,
drives Playwright, probes credentials, calls providers, uploads, downloads, or accesses a network.

Load `references/debug-profile-checklists.md` for debugging or profiling. Load
`references/checklists/scene-debugging.md` for render/runtime defects,
`references/checklists/performance-profile.md` for performance analysis, and
`references/checklists/mobile-input.md` for mobile input or rendering. Load `references/prompt-templates.md` only when
the user requests a reusable prompt or task template.

## Debug Workflow

1. Obtain the exact symptom and any current user-supplied error, screenshot, metrics, device, viewport, or steps.
2. Trace entrypoint, renderer and context ownership, render loop, canvas sizing, camera, scene population, transforms,
   lights, materials, fog, asset URLs, loader callbacks, animation delta units, update order, input registration,
   resize, disposal, and error boundaries from source.
3. For physics or collision defects, trace body, collider, transform, timestep, filtering, event, and cleanup ownership.
4. For audio defects, trace user-gesture unlock, loading, decode, trigger, group volume, pause, restart, and disposal.
5. Enumerate candidate causes and eliminate each with source or user-supplied evidence.
6. Change only the owning module after the root cause is confirmed; never suppress an error or patch around a symptom.
7. Re-read the changed path end to end and state which runtime behavior remains unverified.

## Performance Workflow

1. Treat FPS, frame time, draw calls, triangles, textures, memory, shader cost, bundle size, and network timing as
   runtime evidence only when the user supplies current measurements.
2. Map likely CPU, GPU, memory, and loading costs from source: allocations, traversal, mixers, instancing, resource
   sharing, culling, LOD, DPR, shadows, post-processing, texture formats, and disposal.
3. Recommend one measurable change at a time with the same-scenario metric the user should collect before and after.
4. Never invent a baseline, improvement percentage, device result, or visual equivalence.

## User-Run Verification

If a canonical repository command would help, label it `User-run command`, explain what evidence it should return,
and let the user decide whether to run it. Never execute or describe it as executed.

## Final Report

Lead with the confirmed root cause or, when runtime data is missing, the exact source-level finding and uncertainty.
Report local references, files changed, candidate elimination, source trace, user-supplied baseline and post metrics,
recommended user-run checks, unverified runtime paths, and residual risks.
