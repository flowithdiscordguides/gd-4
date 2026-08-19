---
name: app-readme-standard
description: Mandatory README creation and maintenance for new runnable apps and app changes that affect setup,
  run/build commands, or UI usage. Use for websites, desktop or mobile apps, games, editors, tools, launchers, and
  other user-facing applications so delivery always includes exact terminal commands, explanations, and a UI guide.
---

# App README Standard

Create or update the project-root `README.md` before completing any new runnable app. Also update it whenever an app
change alters installation, environment setup, run/build commands, launch behavior, or the user-facing workflow.

## Requirement 1 — Apply the Standard to Runnable Apps

- Apply this standard to websites, desktop apps, mobile apps, games, editors, tools, launchers, and services with a
  user-facing interface.
- Create `README.md` even when the user does not explicitly request documentation.
- Do not create an app README for a documentation-only or instruction-only repository unless the user requests one.

## Requirement 2 — Establish Commands and Behavior from Source

- Read canonical manifests, task scripts, configuration files, entry points, environment examples, routes, and UI
  source before documenting commands or behavior.
- Use exact commands supported by the project. Never infer commands from framework habits or copy commands from an
  unrelated project.
- If a required run or build command is absent, add the correct project-native command within the authorized task
  scope. If that requires unresolved authority or information, report the precise blocker instead of writing a
  placeholder or invented command.
- Never place secrets, real credentials, private paths, or machine-specific values in the README.

## Requirement 3 — Preserve the Mandatory Section Order

Write the project title as the first level-one heading. Immediately follow it with these level-two sections in this
exact order, with no overview or promotional copy before them:

1. `## Required Terminal Commands`
2. `## Command Explanations`
3. `## User Guide`

Place optional architecture, configuration, troubleshooting, contribution, or license sections after `User Guide`.

## Requirement 4 — Document Every Required Terminal Command

- List commands in the order the user must run them from a clean checkout or newly created project.
- Include every required working-directory change, dependency installation, safe environment-file setup, database
  preparation, development launch, production build, and production start command that applies.
- Use copyable fenced code blocks and identify the directory in which each command runs.
- Separate platform-specific commands only when the project genuinely requires different commands.
- If the technology has no separate build step, state that accurately instead of inventing a build command.
- Do not include Git operations unless the user explicitly requested them.

## Requirement 5 — Explain Commands One for One

- Explain every command from `Required Terminal Commands` in the same order.
- State what the command does, where it must run, what files or artifacts it creates or changes, and when it is needed.
- Identify commands that remain running, open a local server, require a second terminal, or must be repeated after
  configuration changes.
- Keep explanations operational and specific; do not repeat the command text without explaining its effect.

## Requirement 6 — Write the UI User Guide from Actual Behavior

- Explain how to launch or open the interface after the required commands finish.
- Describe the first-use state, primary workflow, navigation, important controls, inputs, outputs, save or export
  behavior, destructive actions, and success confirmation that actually exist.
- Explain loading, empty, validation, disabled, and error states when they affect normal use.
- Use the labels users see in the UI so they can follow the guide without reading source code.
- Do not describe planned, placeholder, disabled, or nonexistent functionality as available.

## Requirement 7 — Maintain Existing README Content

- Preserve accurate and useful existing content, moving it below the three mandatory sections when necessary.
- Remove or correct commands and UI instructions that became stale because of the active task.
- Keep the README consistent with the delivered source; documentation drift means the app task is incomplete.

## Requirement 8 — Verify Before Completion

- Cross-check each documented command against canonical project files and each user-guide step against implemented UI
  source or permitted runtime evidence.
- Follow project restrictions on command execution. When runtime verification is prohibited, perform source-level
  verification and state that limitation without implying the commands were executed.
- Do not call app delivery complete until the required README exists, contains all three sections in order, and matches
  the delivered app.
