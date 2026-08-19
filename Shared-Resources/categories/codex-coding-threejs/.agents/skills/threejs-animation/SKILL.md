---
name: threejs-animation
description: >-
  Implement and audit Three.js AnimationMixer, AnimationClip, AnimationAction, keyframe, skeletal, morph-target, GLTF,
  blending, attachment, root-motion, lifecycle, and performance behavior. Use threejs-procedural-animation instead for
  oscillator, spring, noise, follow, or other code-driven transform motion that does not depend on clips or mixers.
---

# Three.js Animation

## Governance and Routing

Apply repository governing instructions first. Load the direct reference at
`references/animation-api-and-patterns.md`; never search user-global skill directories. This skill never installs,
executes, builds, tests, starts a server, opens a browser, drives Playwright, calls providers, uploads, downloads, or
accesses a network.

Use this skill for:

- `AnimationClip`, typed `KeyframeTrack` classes, interpolation, and clip utilities.
- `AnimationMixer` ownership, mixer updates, events, caching, uncaching, and teardown.
- `AnimationAction` loops, fades, crossfades, weights, time scaling, and additive layers.
- GLTF clip discovery and binding, skeletal animation, bone attachments, and root motion.
- Morph-target weights driven by clips or coordinated with skeletal clips.
- Animation state machines, transition rules, lifecycle, performance budgets, and source-level diagnosis.

Use `threejs-procedural-animation` instead when the primary behavior is code-driven transform motion such as springs,
oscillation, follow smoothing, noise, bobbing, orbiting, or look-at behavior without clip or mixer ownership. A system
may use both skills when procedural layers augment a clip-driven character, but keep their state and update ownership
explicit.

## Workflow

1. Trace model loading, clip sources, target roots, mixer creation, action caching, update order, state transitions,
   attachments, root motion, morph bindings, and teardown.
2. Define an animation contract: states, clip names, loop modes, transition durations, interruption rules, priorities,
   additive layers, events, and fallback behavior for missing clips.
3. Bind tracks to stable object, bone, material, or morph-target names. Validate names and target roots from current
   source or user-supplied asset metadata.
4. Update each active mixer once per frame with seconds-based delta from the owning loop. Keep mixer time separate
   from fixed-step physics unless the game deliberately synchronizes them.
5. Make transitions deterministic: reset and enable the destination action, set effective time scale and weight, play
   it, then fade or crossfade according to the state contract.
6. Preserve bind-pose ownership when procedural bone layers or attachments coexist with clip playback.
7. Stop actions, remove listeners, call the applicable uncache methods, and release cloned model resources when the
   animated instance is destroyed.
8. Re-read every changed file and trace one complete state transition plus fallback and cleanup paths.

## Verification Boundary

Source inspection can verify clip lookup, target paths, mixer updates, transition order, fallback handling, root-motion
logic, listener cleanup, and resource ownership. Clip presence, deformation quality, foot sliding, timing, visual
blends, runtime errors, and performance require current user-supplied evidence. Mark them unverified otherwise.

If a canonical repository command would help the user collect evidence, label it `User-run command`; never execute or
describe it as executed.

## Final Report

Report the local reference, animation contract, clip and state mapping, mixer ownership, transition rules, root-motion
and morph behavior, lifecycle cleanup, files changed, source-level checks, user-supplied evidence, and remaining
runtime or asset limits.
