# Three.js Animation API and Patterns

## Scope

This reference covers clip-driven Three.js animation: keyframe tracks, mixers, actions, GLTF clips, skeletal rigs,
morph targets, blending, root motion, attachments, lifecycle, and performance. Route code-driven oscillation, springs,
noise, follow smoothing, bobbing, orbiting, and similar transform motion to `threejs-procedural-animation`.

## Core Model

- `AnimationClip` groups named tracks with a duration.
- A `KeyframeTrack` binds timestamped values to a property path under a mixer root.
- `AnimationMixer` evaluates clips for one root hierarchy and advances them with `update(deltaSeconds)`.
- `AnimationAction` is a mixer-local playback instance for a clip and root pair.

Create one mixer per independently animated root. Share immutable clips between compatible instances, but do not share
actions between mixers. Keep mixer creation, frame updates, events, and teardown in one owning system.

## Keyframe Tracks

Choose the track class that matches the target value:

- `NumberKeyframeTrack` for scalar properties and morph-target influences.
- `VectorKeyframeTrack` for positions and scales.
- `QuaternionKeyframeTrack` for rotations; prefer quaternions over Euler component tracks.
- `ColorKeyframeTrack` for color values.
- `BooleanKeyframeTrack` and `StringKeyframeTrack` for discrete boolean or string properties.

Morph targets are numeric weights. Bind them with a `NumberKeyframeTrack`, not a `StringKeyframeTrack`.

```js
const track = new THREE.NumberKeyframeTrack(
  ".morphTargetInfluences[Smile]",
  [0, 0.25, 0.6],
  [0, 1, 0],
);
const clip = new THREE.AnimationClip("Smile", 0.6, [track]);
```

Property paths resolve below the mixer root. Common forms include `.position`, `.quaternion`,
`.material.opacity`, `BoneName.quaternion`, and `.morphTargetInfluences[Name]`. Confirm exact node, bone, and morph
names from current source or supplied asset metadata. A valid clip can silently animate nothing when its path does not
resolve under the selected root.

Use `InterpolateLinear` for most transforms, `InterpolateSmooth` only when cubic behavior suits the authored data,
and `InterpolateDiscrete` for step changes. Do not assume every track type supports every interpolation mode.

## Mixer Ownership and Updates

```js
const mixer = new THREE.AnimationMixer(modelRoot);
const action = mixer.clipAction(clip);
action.play();

function updateAnimation(deltaSeconds) {
  mixer.update(deltaSeconds);
}
```

Advance a mixer once per rendered frame unless the project deliberately synchronizes it to a fixed-step timeline.
Three.js mixer delta values are seconds. Avoid calling both `getDelta()` and `getElapsedTime()` in a way that resets or
advances a shared clock unexpectedly; the owning loop should calculate delta once and pass it to consumers.

Mixer `loop` and `finished` events identify an action. Register stable listener functions so teardown can remove them.
Do not use completion events as the only gameplay authority when a skipped frame, interruption, or teardown must also
resolve the state.

## Action Playback and Transitions

An action retains playback state. Before entering a state, make the destination action usable and deterministic:

```js
function enterAction(next, previous, fadeSeconds) {
  next.enabled = true;
  next.reset();
  next.setEffectiveTimeScale(1);
  next.setEffectiveWeight(1);
  next.play();

  if (previous && previous !== next) {
    previous.crossFadeTo(next, fadeSeconds, true);
  } else {
    next.fadeIn(fadeSeconds);
  }
}
```

Set loop behavior deliberately with `setLoop(mode, repetitions)`. For one-shot actions, pair `LoopOnce` with
`clampWhenFinished = true` only when holding the final pose is desired. An action with zero effective weight, zero
effective time scale, `paused = true`, or `enabled = false` will not behave like a fresh action merely because
`play()` is called.

Crossfades need both actions scheduled on the same mixer and compatible root. The optional warp behavior changes time
scales to align clip durations; enable it only when that transition benefits from duration matching.

## GLTF Animation

`GLTFLoader` returns the scene hierarchy in `gltf.scene` and clips in `gltf.animations`. Bind the mixer to the root
that contains every track target.

```js
function createAnimationSet(gltf) {
  const mixer = new THREE.AnimationMixer(gltf.scene);
  const actions = new Map();

  for (const clip of gltf.animations) {
    actions.set(clip.name, mixer.clipAction(clip));
  }

  return { mixer, actions };
}
```

Never assume the first clip is idle or that provider clip names match gameplay states. Build an explicit mapping and
define a fallback for absent or duplicate names. Inspect duration and track coverage before wiring transitions.

When cloning a skinned character, use the project's established skeleton-aware clone strategy. A shallow hierarchy
clone can leave skeleton references bound to the original instance.

## Skeletal Animation and Attachments

Find the intended `SkinnedMesh` and validate its `Skeleton`, bind pose, bone names, hierarchy, symmetry, and chain
depth. Bone existence alone does not prove deformation quality.

Attach equipment to a named socket or bone under the animated hierarchy. Keep the attachment's local transform in a
data contract, because origin, forward axis, grip pose, and scale vary by asset. Detach or dispose the attachment when
the owning character is destroyed.

Mixer evaluation writes animated bone transforms. If code also changes a bone each frame, define the layer order:

1. Advance the mixer.
2. Apply a constrained procedural offset relative to the evaluated pose.
3. Avoid overwriting the authored base transform with accumulated Euler changes.

Use `SkeletonHelper` only as an explicitly enabled diagnostic and keep it out of release output.

## Morph Targets

`morphTargetDictionary` maps names to influence indices and `morphTargetInfluences` stores numeric weights. Guard both
structures because not every mesh has morph targets and names vary between assets.

For multiple meshes sharing facial targets, bind and update each mesh deliberately. A clip rooted above the meshes can
drive multiple targets when its property paths name the correct descendants. Clamp direct weights when the authored
contract expects the normal zero-to-one range.

Coordinate facial, corrective, and skeletal layers. Additive facial clips should not erase an authored expression or
fight a direct procedural writer for the same influence.

## Additive Animation

Use additive clips for deltas such as breathing, recoil, leaning, or facial overlays. Convert a suitable clip with
`AnimationUtils.makeClipAdditive`, optionally against a known reference frame or clip, before action creation. A clip
authored as an absolute pose is not automatically a valid additive delta.

Normalize layer weights and define priorities. Additive layers can exaggerate translations or rotations when several
actions target the same channels.

## Clip Utilities

- `AnimationClip.findByName(clips, name)` returns a matching clip or `null`.
- `AnimationUtils.subclip(source, name, startFrame, endFrame, fps)` extracts a frame range.
- `AnimationUtils.makeClipAdditive(clip, referenceFrame, referenceClip, fps)` converts against a reference.
- `clip.optimize()` can remove redundant keys; verify it does not alter required authored detail.
- `clip.resetDuration()` recomputes duration from track data.

Treat utility calls as import-time preprocessing where possible rather than repeating them per character.

## Root Motion

Choose one owner for horizontal displacement:

- Gameplay-owned motion removes or neutralizes locomotion root translation and moves the character controller from
  simulation state.
- Animation-owned root motion samples the root delta, applies it through collision-aware gameplay movement, and then
  prevents double application to the rendered hierarchy.

Never combine baked root translation with independent controller movement without an explicit reconciliation step.
Preserve vertical motion only when it matches jump, step, or impact ownership.

## State Machine Contract

For every state record:

- Gameplay predicate and priority.
- Clip name and fallback.
- Loop mode, repetitions, and clamp behavior.
- Entry fade, exit fade, and whether duration warping is allowed.
- Interruptible states and one-shot completion behavior.
- Effective weight, time scale, additive layers, and root-motion policy.

Resolve simultaneous conditions by priority. Avoid restarting the current action every frame; transitions should run
only when the selected state changes or an explicit replay is requested.

## Lifecycle and Cleanup

On instance removal:

1. Remove mixer event listeners.
2. Stop scheduled actions with `mixer.stopAllAction()` when the whole animated root is leaving.
3. Use `uncacheAction`, `uncacheClip`, or `uncacheRoot` according to what will no longer be reused.
4. Remove attachments and helpers.
5. Dispose instance-owned geometry, material, and texture resources through the project's asset ownership rules.

Do not dispose shared clips, geometry, materials, or textures while another instance still uses them.

## Performance

- Share clips and immutable assets across compatible instances.
- Cache action maps; do not search clip arrays or bones in every frame.
- Limit simultaneously active mixers and expensive additive layers.
- Use animation LOD or lower update frequency only with a visible-quality contract.
- Pause or retire animation based on authoritative visibility and lifecycle state, not render callbacks that may be
  skipped or invoked multiple times across passes.
- Avoid per-frame allocations in transition, bone, morph, and root-motion code.

Runtime frame cost and visual equivalence require user-supplied measurements. Source review can verify the presence
and ownership of these safeguards but cannot prove their performance.

## Source-Level Diagnostic Checklist

- Does the mixer root contain every track target?
- Is the mixer updated once with delta seconds?
- Are clip names mapped explicitly with fallbacks?
- Are destination actions reset, enabled, weighted, and played before transition?
- Are one-shots prevented from restarting every frame?
- Are root motion and controller motion reconciled?
- Are procedural bone or morph writers ordered relative to mixer evaluation?
- Are listeners, actions, roots, attachments, and resources cleaned up?
- Are runtime deformation, blend quality, and performance claims limited to user-supplied evidence?
