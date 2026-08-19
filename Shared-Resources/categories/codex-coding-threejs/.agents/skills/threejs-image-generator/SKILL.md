---
name: threejs-image-generator
description: >-
  Plan authorized, user-run 2D asset generation and integrate supplied concepts, texture references, skies, decals,
  logos, icons, GUI art, title art, and image-to-3D references into Three.js projects.
---

# Three.js Image Generator

## Governance and Authorization

Apply repository governing instructions first. Read sibling skills only from `../<skill-name>/SKILL.md`; never search
user-global skill directories. This skill never probes credentials, sources shell profiles, executes scripts, calls a
provider, uploads an image, downloads output, uses credits, installs, builds, tests, launches, opens a browser, or
accesses a network.

External image generation is optional. Before preparing provider-specific guidance, require explicit user
authorization for the provider, exact source images that may leave the repository, intended transformation,
credential use, destination path, retention expectations, and possible credit or plan use. Never inspect or report
secret values. The user owns every provider action and may return sanitized task metadata and local output paths.

## Use Cases

- Character, creature, vehicle, building, weapon, prop, pickup, terrain, or style references.
- PBR-oriented material references, trim sheets, decals, signs, and surface families.
- Skies, backdrops, horizons, menu plates, and parallax layers.
- Logos, faction marks, icons, badges, panels, title art, and marketing stills.
- User-authorized edits, cleanup, palette alignment, variants, and image-to-3D inputs.

Image generation is never mandatory for a premium-quality claim. Use repository assets or authored code-native
visuals when they better fit the product and workflow.

## Asset Brief and Prompt Design

Define purpose, target surface, art direction, composition, dimensions, alpha needs, color space, tiling, text policy,
small-size readability, and runtime format before preparing a prompt.

- Image-to-3D references need one centered, fully visible object, a clean silhouette, clear material zones, neutral
  lighting, minimal perspective distortion, and no fused props.
- Rigging references need a full body, symmetric T- or A-pose, separated limbs, visible hands and feet, and consistent
  front, side, or back views when multiple views are requested.
- Material references need orthographic presentation, controlled value variation, no baked directional shadows, and
  clear separation between albedo intent and height, roughness, or normal interpretation.
- UI assets need a distinctive silhouette, high contrast at final size, transparent-edge discipline, accessible
  state variants, and no tiny generated text.
- Background plates need layered depth, a readable horizon or focal region, and composition that leaves gameplay and
  UI legible.

## User-Run Provider Plan

When authorization exists, provide a reviewable plan containing the sanitized prompt, authorized inputs, requested
dimensions and format, user-owned provider steps, repository destination, and acceptance criteria. Do not provide or
perform credential probes, provider calls, uploads, downloads, or automated file processing.

Provider models, resolution labels, quotas, formats, and costs can change. Use only current user-supplied provider
evidence for those details; otherwise label them unverified.

## Three.js Integration

- Keep concept sources separate from runtime assets.
- Use PNG or WebP when alpha is required. Prefer project-supported WebP, JPEG, AVIF, or KTX2 for large opaque runtime
  textures according to quality and compatibility needs.
- Set color space intentionally: color textures and UI typically use sRGB; data textures remain non-color data.
- Audit dimensions, memory footprint, mipmaps, filtering, wrapping, anisotropy, UVs, seams, alpha fringes, atlasing,
  compression, and responsive crop behavior.
- Never place provider credentials or provider calls in client-side code.
- Load `../threejs-3d-generator/SKILL.md` only for a user-requested manual image-to-3D workflow.

## Verification and Report

Source inspection can verify asset paths, loader settings, color-space configuration, material binding, responsive
usage, fallbacks, and disposal. Provider output, image quality, generated text, tiling, alpha edges, in-game appearance,
and performance require current user-supplied evidence. Mark them unverified otherwise.

Report authorization scope, asset brief, sanitized prompt, intended destination, user-supplied local outputs,
integration decisions, source-level checks, compression or cleanup needs, and remaining runtime/provider limits.
