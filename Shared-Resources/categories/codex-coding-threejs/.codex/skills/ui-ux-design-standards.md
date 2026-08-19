---
name: ui-ux-design-standards
description: The user's product design standards for modern, purpose-fit, visually excellent UI/UX work.
---

# UI/UX Design Standards

Every user interface you design, edit, audit, or rebuild must comply with these standards. These standards
exist because functional code with weak UI is not finished product work.

---

## Standard 1 - Purpose-Fit Design Before Visual Styling

- Identify what the product is, who uses it, what they are trying to accomplish, and what context they are
  in before choosing layout, density, colors, typography, motion, or controls.
- The interface must fit the domain. A developer tool, admin panel, editor, CRM, launcher, game tool,
  dashboard, commerce surface, portfolio, entertainment app, and landing page should not feel interchangeable.
- Do not apply generic SaaS cards, oversized hero sections, glass panels, neon gradients, or playful visuals
  unless they serve the product's purpose.
- If the user gives a rough request, translate it into the most useful product experience implied by the request.
  Do not require the user to design the interface for you.
- Ask a question only when a missing answer would create a real product, security, data, or accessibility risk.

---

## Standard 2 - Modern Product Quality Bar

- The visual result must feel current, intentional, and polished by modern product standards.
- Avoid Windows XP, Windows 7, default browser, raw Bootstrap, unstyled form, and template-demo aesthetics.
- Avoid "vibe coded" decoration that looks impressive for five seconds but weakens usability, hierarchy,
  responsiveness, accessibility, or implementation quality.
- Every screen should have a clear visual hierarchy, confident spacing, consistent alignment, and a restrained
  component system.
- The UI should make users think the product is clean, capable, and carefully designed, not that it contains
  many unrelated controls competing for attention.

---

## Standard 3 - Workflow Clarity Over Button Count

- Each primary workflow must have one obvious next action and a small number of meaningful secondary actions.
- Do not create many buttons that duplicate the same behavior or make the user choose between unclear actions.
- Use progressive disclosure for advanced, destructive, rare, or highly detailed controls.
- Use tabs, segmented controls, menus, drawers, command palettes, inspector panels, or contextual toolbars when
  they reduce clutter and match the workflow.
- If the request is "add a button," design the correct control for the job. A text-only oversized rectangle is
  not acceptable when an icon button, compact action, toggle, segmented control, or contextual menu is the
  better product pattern.

---

## Standard 4 - Control Semantics

- Match each interaction to the control users already understand:
  - Use icon buttons for compact tool actions.
  - Use text buttons for clear commands that need labels.
  - Use icon-plus-text buttons for primary actions where recognition and clarity both matter.
  - Use segmented controls for mutually exclusive modes.
  - Use toggles or checkboxes for binary settings.
  - Use sliders, steppers, or numeric inputs for adjustable values.
  - Use menus for option sets that do not deserve permanent screen space.
  - Use tabs for switching between peer-level views.
  - Use swatches for color selection.
- Buttons must not resize, wrap awkwardly, or dominate the layout unless the product context truly calls for it.
- Destructive actions must be visually and behaviorally distinct from primary actions.
- Disabled states must explain unavailable behavior through placement, tooltip text, or surrounding context.

---

## Standard 5 - Icons, Imagery, and Visual Assets

- Prefer established icon libraries already present in the project. If none exists and icons are needed, propose
  a specific open-source icon dependency in the execution plan instead of drawing poor custom SVG icons.
- Do not create crude hand-drawn SVG icons when a mature icon set, product asset, or generated bitmap image would
  produce a better result.
- Icons must be visually consistent in stroke width, corner radius, size, alignment, and metaphor.
- Use tooltips or accessible labels for icon-only controls whose meaning is not universally obvious.
- Websites, apps, games, product pages, portfolios, and visual tools should use meaningful imagery or rich
  visual assets when that helps the user understand or feel the product.
- Avoid stock-like, blurry, overly dark, purely atmospheric, or unrelated images when the user needs to inspect
  an actual product, place, object, state, person, or gameplay surface.

---

## Standard 6 - Layout, Spacing, and Density

- Use layout density appropriate to the work. Operational tools should be compact, scannable, and efficient.
  Editorial or promotional pages may breathe more, but must still reveal useful content quickly.
- Do not put cards inside cards. Use cards only for repeated items, modals, inspectors, contained tools, or
  genuinely grouped records.
- Page sections should be full-width bands or unframed layouts with constrained inner content.
- Use stable dimensions for boards, toolbars, icon buttons, counters, tiles, previews, and fixed-format UI so
  labels, hover states, loading states, and dynamic content do not shift the layout.
- Text must fit inside its parent at mobile and desktop sizes. Do not rely on viewport-scaled font sizes.
- Do not let UI elements overlap in an incoherent way. If a layout can overlap at realistic content lengths,
  redesign the layout.

---

## Standard 7 - Typography and Readability

- Use type scale intentionally. Hero-scale type belongs only in true hero moments, not compact panels, tools,
  cards, sidebars, or dashboards.
- Use smaller, tighter headings inside dense app surfaces.
- Do not use negative letter spacing. Letter spacing should be `0` unless the existing design system requires
  another value.
- Maintain readable line length, contrast, and hierarchy across viewport sizes.
- Labels, helper text, empty states, and error messages must be concise and useful.
- Do not add visible in-app text explaining the application's features, keyboard shortcuts, visual style, or how
  to use obvious controls unless that text is part of a real onboarding or documentation surface.

---

## Standard 8 - Color, Materials, and Visual Restraint

- Build a palette that supports meaning, hierarchy, and mood instead of saturating the interface with one hue.
- Avoid one-note palettes dominated by only purple, blue-purple gradients, beige, cream, tan, brown, orange,
  espresso, dark blue, or slate unless the product identity specifically demands it.
- Avoid discrete decorative orbs, gradient blobs, bokeh blobs, random glow patches, and background effects that
  do not support the product.
- Use depth, borders, shadows, translucency, and blur sparingly and consistently.
- A breathtaking interface is not necessarily loud. It can be quiet, exact, and deeply polished.
- Color must never be the only way to communicate state.

---

## Standard 9 - Responsive and Accessible by Default

- Every UI must be designed for mobile and desktop unless the product is explicitly single-device.
- Touch targets, pointer targets, keyboard focus, hover states, active states, loading states, empty states, and
  error states are part of the design, not afterthoughts.
- Interactive elements must have accessible names.
- Important flows must be usable with keyboard navigation where the platform supports it.
- Text and controls must maintain sufficient contrast in normal, hover, selected, disabled, and error states.
- Motion must be purposeful and should respect reduced-motion preferences when implemented.

---

## Standard 10 - Landing Pages, Heroes, and First Viewport

- Do not create a landing page when the user asked for an app, tool, game, editor, dashboard, or usable product
  experience. Build the usable product as the first screen.
- When a landing page is actually requested, make the first viewport communicate the real product, brand, person,
  place, object, or offer immediately.
- For landing-page heroes, the headline should be the brand, product, place, person, or literal offer category.
  Put value propositions in supporting copy.
- Use a real or generated bitmap image, product visual, actual media, gameplay scene, or immersive interactive
  scene when a hero needs media. Do not use generic SVG hero illustrations or gradient-only hero backgrounds.
- Hero content must leave a hint of the next section visible on mobile and desktop, including wide desktop.

---

## Standard 11 - Implementation Discipline for Design Work

- Use the project's existing design system, component library, icon library, CSS architecture, and framework
  patterns before introducing new ones.
- If the project has no usable design system, establish a small coherent set of tokens for spacing, radius,
  type, color, shadows, borders, states, and motion.
- Do not hard-code scattered magic values when design tokens or local CSS variables would make the interface
  more consistent.
- Do not create placeholder UI, placeholder data, fake controls, or unfinished interaction states unless the user
  explicitly asks for a static mockup.
- If an additional dependency is needed for high-quality icons, charts, 3D, animation, or UI primitives, add it
  only to the manifest with a pinned version and list the manual install command in the execution plan.

---

## Standard 12 - UI/UX Self-Audit for Existing AI-Generated Projects

- When inspecting an existing project, look for signs of weak AI-generated UI:
  - Generic card-heavy layout with little product-specific purpose.
  - Too many buttons, duplicated actions, or unclear hierarchy.
  - Oversized text-only controls where precise controls belong.
  - Default form styling, raw browser controls, or old desktop visual language.
  - Inconsistent spacing, typography, icon styles, radius, shadows, or colors.
  - Poor responsive behavior, clipping, awkward wrapping, or layout shifts.
  - Decorative gradients, blobs, or SVG art that do not improve the product.
- If the design appears AI-generated and falls below these standards, ask one concise question before expanding
  scope: "This UI looks AI-generated and below your design bar. Do you want me to include a UI/UX pass?"
- If the user says yes, do not ask a long questionnaire. Infer the product purpose from the code and request, then
  make the interface purpose-fit, visually excellent, and easier to use.
- If the user says no, preserve the current visual design and complete only the requested non-design work.

---

## Standard 13 - Design Planning Requirements

- For any UI task, the execution plan must include a short design intent describing:
  - The product surface being changed.
  - The target user or workflow.
  - A distinctive art direction and visual thesis explaining why it belongs to this specific product.
  - The signature visual moment, composition, interaction, or asset that will create memorable impact.
  - The key controls and interaction states that will be implemented.
  - Any assets or icon dependencies required.
- The plan must record the selected concept and why its product fit, memorability, accessibility, and implementation
  feasibility are stronger than the rejected directions.
- The plan must not force the user to make design decisions you can correctly infer from the project.
- The plan must identify if the request affects responsive behavior, accessibility, or primary workflow clarity.

---

## Standard 14 - Final Design Audit

Before reporting UI work complete, audit the result against this checklist:

- The design fits the product's actual purpose and target workflow.
- The primary action is obvious and secondary actions are controlled.
- There are no unnecessary duplicate buttons or confusing control clusters.
- Icons are consistent, accessible, and not crude custom drawings.
- Typography, spacing, color, radius, shadow, and borders feel like one system.
- The screen has a memorable focal point or signature visual idea and does not feel interchangeable with a routine
  corporate tool, generic template, or cubicle-designed utility.
- The UI avoids old desktop aesthetics and generic template styling.
- The layout works at realistic mobile and desktop sizes.
- Text does not overflow, clip, or overlap.
- Loading, empty, error, hover, focus, selected, disabled, and destructive states are handled when relevant.
- The implementation uses existing project patterns and avoids placeholder design work.

If the audit fails, do not call the work complete. Fix the design or report the blocker clearly.

---

## Standard 15 - Design Audit Output Requirements

When the user asks for a UI/UX audit, do not stop at findings. A design audit must diagnose the current
interface and define the destination the product should move toward.

Every UI/UX audit must include these sections:

- **Product read:** State what the product is, who it serves, and the core workflow the interface should make
  feel simple, confident, and safe.
- **Current-state findings:** List the concrete UX, visual, accessibility, responsiveness, and interaction
  problems in severity order with file or screen references when available.
- **Design direction:** Describe how the product should feel after the redesign, using domain-specific language
  instead of generic phrases like "modern and clean."
- **Workflow redesign:** Explain how the primary user flow should be reorganized, including what becomes
  primary, secondary, hidden, confirmed, or removed.
- **Layout plan:** Describe the target information architecture, major regions, spacing density, responsive
  behavior, and how realistic content should fit without clipping or clutter.
- **Control model:** Name the correct controls for important actions and settings, including destructive
  actions, mode switching, search/filtering, empty states, and advanced options.
- **Visual system:** Define the intended typography, color role, surface treatment, radius, borders, shadows,
  icon approach, and state styling at the level needed to guide implementation.
- **Interaction states:** Call out loading, empty, error, success, selected, hover, focus, disabled, and
  destructive states that the redesign must handle.
- **Implementation plan:** Provide phased steps that can be implemented without guessing. Each phase should
  name the files or components likely to change when that can be known from the audit.
- **Expected result:** Summarize what the user experience will feel like after the redesign and why it fits the
  product's purpose.

If the audit identifies weak UI but does not include a concrete redesign plan, the audit is incomplete. Ask
whether the user wants implementation only when scope, file edits, or verification need approval; do not ask the
user to invent the design direction that the standards require you to provide.

---

## Standard 16 - Agent-Owned Visual Verification

The user is not responsible for proving that an interface looks bad. User-provided screenshots are optional
evidence, not a required input. The agent owns visual quality verification.

Before implementing UI changes, define concrete visual acceptance criteria for the exact product surface:

- Overall composition: what the first viewport or primary window should contain, emphasize, and de-emphasize.
- Density and spacing: how much empty space is intentional, where content should sit, and how groups align.
- Component treatment: how buttons, fields, tabs, lists, cards, panels, notices, and destructive actions differ.
- Typography: the size, weight, hierarchy, and tone of titles, labels, helper text, metadata, and empty states.
- Color roles: background, surface, border, primary action, destructive action, selected state, notice tones,
  and muted text.
- Responsive behavior: how the layout changes when the window or viewport is narrow, short, or content-heavy.
- Native/toolkit styling: how default controls are replaced, restyled, or wrapped so the app does not look raw.

During implementation, do not rely on code changes as proof that the design improved. Verify the result through
the strongest available method:

- If running or previewing the app is allowed, launch the UI through the approved command, inspect it visually,
  and capture screenshots when the environment supports that workflow.
- If running is not allowed, perform a source-level visual audit against the acceptance criteria and report that
  runtime visual verification was not performed.
- If the user provides a screenshot, treat it as evidence that overrides optimistic assumptions from code.
- If no screenshot exists and runtime inspection is not allowed, do not ask the user to provide one. Be more
  conservative, inspect the layout code harder, and avoid claiming visual excellence without visual evidence.

UI work is not complete if the result still has raw toolkit controls, default browser styling, weak hierarchy,
misaligned regions, accidental empty space, cramped fields, unclear primary action, inaccessible state feedback,
or an unfinished desktop-demo feel. In that case, continue the redesign within the approved scope or report the
remaining design blocker clearly.

Native desktop apps need the same visual bar as web apps. For egui, GTK, Qt, native widgets, or immediate-mode
toolkits, explicitly design spacing, fonts, colors, control hierarchy, panels, scroll regions, responsive
constraints, and empty states. A raw toolkit surface is not an acceptable finished design.

---

## Standard 17 - Modern Purpose-Built Composition

Modern, visually pleasing, breathtaking design is mandatory. Do not use "avoid dashboards" as an excuse to make
plain, basic, empty, old-fashioned, or underdesigned UI. The failure is not modern visual language; the failure
is generic dashboard clustering that makes the product harder to understand and use.

Before choosing a layout pattern, identify the product's real workflow shape:

- Reading: where existing information is scanned, selected, compared, or inspected.
- Writing: where new information is entered, edited, validated, and saved.
- Transition: how the interface moves between locked, empty, selected, editing, and saved states.
- Priority: what the user should see first, what is secondary, and what should be hidden until needed.
- Completion: what confirms that the user's action succeeded and what the next useful action is.

Choose the composition that fits that workflow. A dashboard layout is valid only when the product is truly a
dashboard with multiple peer-level metrics or monitoring surfaces. For tools, editors, vaults, launchers,
generators, games, and focused apps, prefer purpose-built patterns such as master-detail, command workspace,
focused editor, split inspector, timeline, canvas, queue, library, or task flow when those fit the job better.

The interface must not feel basic. "Clean" means crafted, not empty. A polished screen needs intentional
composition, hierarchy, spacing rhythm, typography, color roles, component states, and product-specific visual
language. Avoid oversaturated color, random decoration, template-dashboard panels, raw toolkit controls, default
browser styling, decorative noise, and vibe-coded effects that do not help the workflow.

Audit alignment before calling UI work complete:

- Button edges, input edges, labels, panel edges, gutters, baselines, and action groups must line up
  intentionally.
- Primary actions must be visually connected to the region they affect.
- Mode controls, search fields, create buttons, destructive buttons, and status indicators must not float in
  unrelated positions.
- Related fields should read as one form. Unrelated actions should not appear inside the same visual group.

Audit information flow before calling UI work complete:

- The user must immediately understand where to read existing information and where to enter new information.
- Empty states must explain the next useful action without turning into filler copy.
- Primary forms should not be trapped in scroll regions when the viewport has enough space to show them.
- Scroll should belong to naturally long content such as lists, logs, tables, histories, or advanced settings.
- Dead lower-page or lower-window space is a design failure unless it intentionally supports focus, inspection,
  a canvas, a preview, or future content that is visibly represented.

User-specified visual behavior must be implemented exactly. If the user asks for randomized per-character
animated color changes, implement independent character-level color changes. Do not replace that request with
waves, pulses, shimmer, generic glow, marquee effects, or unrelated animation.

Screens that contain misaligned buttons, unclear read/write flow, accidental scroll panels, wasted dead space,
generic dashboard clustering, weak header treatment, or ignored animation specifics fail this standard even if
the code technically works.

---

## Standard 18 - Expressive Art Direction and WOW Factor

Every app must aim to visually impress, regardless of how small or utilitarian its workflow is. Simplicity may reduce
the number of elements, but it must increase the intentionality, craft, and expressive force of the elements that
remain. Functional correctness and clarity are the foundation, not the visual finish line.

- Before selecting an art direction, generate at least three genuinely distinct concepts. They must differ in
  composition, typography, color or material language, signature interaction, and asset strategy—not merely palette.
- At least one concept must challenge the obvious layout while remaining usable. Compare concepts for product fit,
  workflow clarity, memorability, accessibility, responsive behavior, and implementation feasibility.
- Select the strongest direction from evidence and carry its visual thesis through the entire surface. Ask the user
  only when the alternatives create a material brand, scope, or risk decision that cannot be inferred safely.
- Establish a product-specific art direction before styling. Define the emotional character, visual metaphor,
  composition language, typography attitude, color energy, material treatment, and motion behavior that make the app
  recognizable without its logo.
- Build at least one signature experience that earns attention: a striking first composition, expressive data or
  canvas treatment, purposeful animation, rich empty state, distinctive navigation transition, bespoke illustration,
  atmospheric depth, tactile control response, or another domain-appropriate focal moment.
- Make the interface feel alive through meaningful state transitions, responsive feedback, layered composition,
  intentional rhythm, and carefully chosen imagery or generated visual assets when they strengthen the product.
  Respect reduced-motion preferences and never trade legibility, accessibility, or workflow speed for spectacle.
- Reject the safe corporate default: generic sidebars, interchangeable cards, timid color, default typography, flat
  utility layouts, decorative gradients with no concept, and polished-but-anonymous component arrangements.
- Visual richness must communicate purpose. Every dramatic choice must reinforce hierarchy, mood, orientation,
  storytelling, feedback, or comprehension rather than becoming unrelated decoration.
- A simple app still requires a visual thesis and signature moment. "There is not much content" is not permission to
  deliver a dull, empty, generic, or merely competent screen.
- Final verification must ask whether the result is memorable, emotionally intentional, unmistakably suited to its
  product, and strong enough to make a user pause positively. If the honest answer is no, the UI is not complete.
