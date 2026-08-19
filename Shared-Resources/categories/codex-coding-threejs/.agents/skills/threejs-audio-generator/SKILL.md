---
name: threejs-audio-generator
description: >-
  Plan authorized, user-run game-audio creation and integrate supplied SFX, ambience, UI sounds, voice, cleaned audio,
  manifests, buses, triggers, loops, unlock behavior, and lifecycle-safe Web Audio into Three.js games.
---

# Three.js Audio Generator

## Governance and Authorization

Apply repository governing instructions first. Read references only from `references/` beside this file; never search
user-global skill directories. This skill never probes credentials, sources shell profiles, executes scripts, calls a
provider, uploads voice or audio, downloads output, uses credits, installs, builds, tests, launches, opens a browser,
or accesses a network.

External audio generation is optional. Before preparing provider-specific guidance, require explicit user
authorization for the provider, exact text or audio inputs that may leave the repository, intended operation,
credential use, destination path, voice-consent and licensing status, retention expectations, and possible credit or
plan use. Never inspect or report secret values. The user owns every provider action.

## Use Cases

- SFX for movement, impacts, weapons, pickups, collisions, abilities, confirmations, errors, and UI controls.
- Loopable ambience, machinery, weather, crowds, environmental beds, and music-layer hooks.
- Announcer lines, dialogue, accessibility narration, user-authorized voice conversion, and cleanup.
- Runtime manifests, buses, priorities, concurrency limits, spatialization, pause/resume, volume, mute, and cleanup.

Audio matters to game feel, but external generation is never mandatory for a premium-quality claim. Repository-owned,
user-supplied, open-licensed, or procedural Web Audio sources may be better choices.

## Reference Gate

Load `references/audio-workflows.md` before planning multiple assets, voice processing, runtime integration, or a
premium audio pass. Record the exact repository-local path and any read failure. An unavailable reference limits the
affected claim; it does not authorize global search or invented provider details.

## Audio Brief and Matrix

Define each sound's gameplay event, purpose, priority, duration, transient shape, loop behavior, spatial mode,
concurrency, ducking, volume bus, variation strategy, cleanup owner, and fallback. Cover at least primary input,
success, damage or failure, reward, UI confirm and cancel, pause, retry, and ambience when those states exist.

For voice, document the exact approved script, pronunciation, emotional direction, language, accessibility role,
speaker consent, usage rights, and whether timing must follow a user-supplied performance.

## User-Run Provider Plan

When authorization exists, provide a reviewable plan containing sanitized prompts or text, authorized input files,
requested format and duration, user-owned provider steps, repository destinations, and acceptance criteria. Do not
provide or perform credential probes, provider calls, uploads, downloads, validation calls, or automated processing.

Provider voices, models, quotas, formats, limits, and costs can change. Use only current user-supplied provider
evidence for those details; otherwise label them unverified.

## Runtime Integration

- Keep credentials and provider calls out of browser code; load committed or otherwise repository-resolved assets.
- Unlock the audio context from a real user gesture and expose clear fallback state when unlock or decode fails.
- Separate master, music, ambience, SFX, UI, and voice buses when the game needs independent control.
- Define concurrency and priority so repeated events do not clip, mask critical feedback, or grow unbounded nodes.
- Make loops seamless at the source or with deliberate overlap; stop and dispose them on state exit and teardown.
- Drive audio from authoritative gameplay and UI events, not polling or duplicated rules.
- Persist volume and mute through the project's established settings path and respect reduced sensory preferences.
- Trace asset loading, decode errors, pause/resume, restart, tab visibility, and disposal ownership.

## Verification and Report

Source inspection can verify manifests, event wiring, buses, unlock flow, fallbacks, settings, lifecycle, and cleanup.
Provider success, voice identity, licensing, audio quality, loop seams, loudness, decode, playback, spatial perception,
and performance require current user-supplied evidence. Mark them unverified otherwise.

Report authorization scope, local reference ledger, audio matrix, sanitized prompts or scripts, user-supplied local
outputs, runtime mapping, source-level checks, licensing assumptions, and remaining audio/provider limits.
