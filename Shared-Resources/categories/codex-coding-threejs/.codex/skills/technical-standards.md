---
name: technical-standards
description: Engineering standards for all code produced in the user's projects.
---

# Technical Standards

Every file you write, edit, or generate must comply with these standards. No exceptions.

---

## Standard 1 — Code Discipline (Full Implementation, Zero Placeholders)

- **Write complete code.** Every function, every class, every module — fully implemented.
- **No placeholder comments.** The following patterns are banned:
  - `// TODO: implement this`
  - `# ... rest of implementation`
  - `/* placeholder */`
  - `pass  # implement later`
  - `throw new Error("not implemented")`
- **No ellipsis blocks.** Do not use `...` to abbreviate code in files you are writing or editing. If you are outputting a file, output the entire file.
- **No stub functions.** If a function signature exists, its body must be complete.
- If full implementation is genuinely blocked (missing spec, external dependency not yet available), state the blocker explicitly and wait for the user's direction. Do not fill the gap with a stub.

---

## Standard 2 — Modular Architecture

- **Maximum 400 lines of code per file.** This is the hard ceiling, not a target. If a file reaches 400 lines during implementation, you must stop and modularize before writing another line. See the modularization procedure below.
- **Single responsibility per module.** One file does one thing well.
- **Explicit imports.** No wildcard imports (`from x import *`). Name every dependency.
- **Flat over nested.** Prefer shallow directory structures. Deep nesting (>3 levels) requires justification.
- **Naming conventions:**
  - Files: `kebab-case` (e.g., `auth-handler.ts`, `data-parser.py`).
  - Classes: `PascalCase`.
  - Functions/variables: `camelCase` (JS/TS) or `snake_case` (Python).
  - Constants: `UPPER_SNAKE_CASE`.

### Modularization Procedure

When a file reaches or exceeds 400 lines of code during implementation:

1. **Stop writing.** Do not add more code to the file.
2. Identify the logical boundaries in the file. Look for groups of related functions, a class that could be extracted, or a section of utilities that serve a different purpose than the file's primary responsibility.
3. Create a new file with a descriptive `kebab-case` name that reflects the extracted responsibility.
4. Move the extracted code into the new file.
5. Update all import statements in every file that referenced the moved code. Verify that no import is broken.
6. Verify that both the original file and the new file are under 400 lines.
7. Log both files in the matching task-scoped `.codex/progress-history-[task].md` file as `FILE_CREATED` and `FILE_MODIFIED`.

Do not ask for permission to modularize. This is a standing instruction. When the 400-line limit is hit, modularization is mandatory and immediate.

---

## Standard 3 — Inline Comments

Every file you write must include inline comments that explain the purpose and logic of the code. This is not optional.

- **Every function** must have a comment above it explaining what it does, what its parameters are, and what it returns.
- **Every class** must have a comment above it explaining its responsibility and how it fits into the broader module.
- **Every conditional block** (if/else, switch, ternary) that involves business logic must have a comment explaining the reasoning behind the condition.
- **Every loop** that does more than trivial iteration must have a comment explaining what it is iterating over and why.
- **Every non-obvious expression** (regex patterns, bitwise operations, complex math, chained method calls longer than 3 methods) must have a comment explaining what it produces.
- **Every import section** at the top of a file must have a brief comment grouping imports by purpose if there are more than 5 imports (e.g., `// React core`, `// Utility functions`, `// Type definitions`).
- **Every constant or configuration value** must have a comment explaining what it controls and why it is set to that value.

Comments must be written in plain English. They must explain WHY, not just WHAT. A comment that restates the code (e.g., `// increment counter` above `counter++`) is useless. A comment that explains intent (e.g., `// Track failed login attempts to trigger lockout after 5 tries`) is useful.

---

## Standard 4 — Strict File Isolation

- **Write only to the designated project directory.** Do not create or modify files outside the active project root (exception: task-scoped `.codex/progress-history-[task].md` and `.codex/learned-history-[task].md` files).
- **No writes to system directories** (`/tmp`, `/var`, `/etc`, `~/.config` of unrelated tools, etc.) unless the user explicitly directs it.
- **No writes to other project folders.** Each project is sandboxed. Cross-project file operations require explicit permission.
- **Git hygiene:** Do not commit secrets, build artifacts, or environment files. If a `.gitignore` does not exist, create one before the first file is written. The `.gitignore` must exclude at minimum:
  - `node_modules/`
  - `.env`
  - `.env.local`
  - `.env.*.local`
  - `dist/`
  - `build/`
  - `.vscode/` (unless project-specific settings are intended)
  - `*.log`
  - `.DS_Store`
  - `__pycache__/`
  - `venv/`
  - `.venv/`

---

## Standard 5 — Error Handling

- Handle errors at the boundary where they occur. Do not swallow exceptions silently.
- Use typed/structured errors over generic error strings where the language supports it.
- Log errors with enough context to diagnose without reproducing (timestamp, operation, input summary).
- Never expose stack traces or internal paths to end users in production code.
- Every async operation (API calls, file reads, database queries) must have explicit error handling. No unhandled promise rejections. No bare `try {} catch {}` with an empty catch block.

---

## Standard 6 — Dependency Awareness

When adding a dependency to a manifest file (package.json, requirements.txt, etc.):

- The dependency must be open-source unless the user has explicitly approved a paid alternative.
- The dependency must not introduce known critical security vulnerabilities at the time of selection.
- Pin the dependency to a specific version or version range. Do not use `latest` or unpinned references.
- Include a comment in the plan explaining why this dependency is needed and what it replaces (if anything).
- Prefer packages that include their own type definitions (TypeScript types shipped in the package) over packages that require a separate `@types/` installation, when both options are functionally equivalent.
- Remember: you are never allowed to install dependencies. You add them to the manifest. The user installs them. This is Law 3 in user-laws.md and it is absolute.

## Standard 7 — Canonical Sources and Current Technical Facts

- Establish the project's present state from canonical project files such as manifests, lock-state evidence,
  configuration, entry points, and current source. Do not infer it from model memory, stale prompts, copied setup
  guides, task-history claims, search snippets, or naming conventions.
- When external current information materially affects implementation, verify it with official primary sources through
  an approved research capability. This includes current package versions, framework templates, APIs, operating-system
  requirements, product behavior, security advisories, command syntax, and platform policies.
- Clearly separate installed state, declared state, newest externally available state, and the proposed target state.
  Never silently upgrade a dependency, command, template, configuration, or behavior to the newest external version.
- When external research changes a technical decision, identify the exact official source in the plan or report and
  state what decision it changed. If authoritative verification is unavailable, state the precise uncertainty.
- Do not perform external research when current project source and stable technical facts fully establish the answer.
- Research does not authorize dependency installation, Git operations, code execution, or any other prohibited action.

## Standard 8 — Categorical Neighbors and Feature Integration

Before implementing a feature, setting, control, workflow, visual behavior, or Three.js system, search current source
and relevant task history for categorical neighbors. Search by purpose and implementation shape, not only by the
user's exact name.

- Inspect analogous settings, components, controls, routes, state, handlers, persistence, validation, error handling,
  permissions, styling, design tokens, assets, tests, registration points, render ownership, and documentation.
- Map what the new behavior shares with existing features and what is genuinely distinct. Reuse or extend a shared
  abstraction when semantics and lifecycle match; keep implementations separate when forced reuse would couple
  unrelated behavior or weaken clarity.
- Similar user-facing settings must align with established naming, defaults, data shape, save behavior, feedback,
  accessibility, layout, and styling unless the requested behavior requires a documented difference.
- Trace every discovery and registration surface so a feature is integrated into the complete system rather than
  added as an isolated control, duplicate configuration path, parallel style system, or disconnected handler.
- For Three.js work, explicitly trace renderer, scene, camera, loop, controls, resize, asset, animation, material,
  depth/normal/velocity, post-processing, disposal, diagnostics, and gameplay/UI event ownership when relevant.
- Record the categorical neighbors found and the evidence-based reuse or separation decision in task progress before
  editing. Preserve reusable findings in learned history.
- During verification, confirm the new work did not duplicate an existing capability, fork shared styling or render
  state without a reason, bypass common validation or persistence, or regress an adjacent consumer.

## Standard 9 — Shared-System Regression Impact Matrix

Before editing shared behavior, record this matrix in the matching progress history:

| Neighbor or shared system | Current behavior or invariant | Planned interaction | Verification evidence |
| --- | --- | --- | --- |
| [Feature, component, handler, state, persistence, styling, render owner, or prior fix] | [What must remain true] | [Reuse, extension, or deliberate separation] | [Source trace and permitted check] |

- Include every categorical neighbor, reused abstraction, affected shared system, and relevant bugfix regression
  contract. An empty matrix is allowed only when current-source and history searches establish that none exist.
- After editing, verify each row against current source and every permitted check. Record the result in progress
  history; an unverified row prevents a completion claim.
- When one change affects several consumers, verify the shared implementation and each materially distinct consumer
  path instead of assuming the shared edit proves every integration.

## Standard 10 — Subagent Editing and File-Length Verification

- Only the approved implementer subagent may write code. Every other project subagent is read-only and may return
  evidence, plans, designs, or review findings only.
- Before an assigned edit, the implementer must obtain the exact current line count of every target file with an
  approved read-only inspection command. It must not add to a file that is already at the modularization boundary.
- The implementer must use `apply_patch` for authorized edits. Shell redirection, write commands, formatters, code
  generators, scripts, runtimes, and task runners are prohibited.
- After each edit, the implementer must re-read the complete changed file and report its final line count. Any file at
  or above 400 lines requires compliant modularization before the handoff can be accepted.
- The parent Codex agent must independently re-read every subagent-edited file and repeat the line count. A subagent's
  reported count or completion statement is evidence only and never satisfies Law 7 verification.
- Assign exactly one writer to a file at a time. Parallel subagents may analyze the same file, but overlapping writes
  are prohibited.
