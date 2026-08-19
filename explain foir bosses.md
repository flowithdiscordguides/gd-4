# What the App Actually Does

The easiest way I can explain it is that I built two tools that work together to remove a lot of the repetitive work,
screen clutter, and mental clutter that comes with building and managing projects.

- **GitDesk** is the main project organizer. It combines a lot of what I normally need Finder, GitHub Desktop,
  github.com, VS Code, and the terminal to do.
- **App Merger** is the companion app. It lets me stack VS Code windows more like browser tabs, so all of those windows
  do not have to stay spread across the screen.

The apps do not use AI themselves. They organize the work around AI and software development so I can spend less time
setting things up, moving files around, watching builds, and repeating the same steps.

## The Main Problem I Was Trying to Solve

When I get an idea and want to see if I can turn it into a real app, the normal process creates a lot of small tasks.
I have to make folders, find the right skills and documents, copy them into the project, open the project in different
tools, create backups before major changes, move clean code into a GitHub repo, watch builds, and prepare releases.

None of those steps are very hard by themselves, but they add up. They also spread the project across a bunch of
windows and make me remember which folder, version, repo, build, and AI chat is the current one.

GitDesk puts most of that workflow in one place and reduces it to a few button presses.

## What GitDesk Does

### It organizes local projects

GitDesk lets me create a project, create features inside that project, and create numbered versions of each feature.
I only have to type what I want the project or version to be called, and the app handles the folder structure and
numbering.

For example, if I create a project called `Golf Game`, it can automatically create the first feature as `01 init` and
the first version as `v01 init`. When I am ready to work on something new, I can click the new version button, type
`add background NPCs`, and it creates `v02 add background NPCs` for me.

That gives me a clean rollback point before I start another round of changes. It is especially useful when I want to
start a new AI chat with a clean folder and clean context without losing the last working version.

### It creates clean, reusable work environments

I can save parent folders as favorites, so I do not have to keep opening Finder and navigating back to the same places.
I can also save reusable skills and documents in the app and add them to a new project during creation.

That means when I think, "I need a clean environment to test these skills or documents," GitDesk can create it and
prime it with the context I already know I need. After that, I can open the project and start prompting instead of
rebuilding the same setup again.

### It saves disk space when creating versions

Projects made with Node, Rust, and similar tools can have dependency folders that are hundreds of megabytes or several
gigabytes. Normally, copying the whole project into a new version also copies all of those dependencies.

GitDesk lets me choose folders that should move forward instead of being copied. If a Rust dependency folder is 4 GB,
creating another version does not automatically turn that into 8 GB. The new version mainly duplicates the smaller
source and text files while the large dependency folders move to the current version.

### It handles the GitHub workflow

Repo Mode brings the GitHub side of the project into the same app. It can handle the work I would normally split
between VS Code or the terminal, GitHub Desktop, and the GitHub website.

That includes managing the repo, pushing and merging changes, creating tags, monitoring GitHub Actions builds, and
working with releases. If a project builds an EXE, DMG, or AppImage, I can manage that process without constantly
switching between apps and browser tabs.

GitDesk uses GitHub personal access tokens for these features. The tokens are stored in the system Keychain, and the
app can open the GitHub token page with the needed permissions already selected. GitHub organizations can use their
own token while the regular account still manages the sync chain.

### It creates sync chains between projects and repos

Sync chains automate the movement between the local working project, a clean GitHub repo, a private source repo, and a
public release repo.

I can set up sync ignore rules, similar to `.gitignore`, for files that should never leave the local project. I can
also keep the actual source code inside a private GitHub organization while syncing only the finished release binaries
to a public repo. Users can still download and update the app, but the source code does not have to be published with
the release.

This removes a lot of manual copying and pasting while still giving me control over what goes to each destination.

### It handles backups and completion alerts

GitDesk can back up projects and media to any local folder I choose. It also has notifications and optional jingles, so
I can tell when work finishes without constantly watching the app.

## What App Merger Does

App Merger focuses on the window clutter side of the problem. It lets me group VS Code windows more like tabs in a web
browser instead of leaving every project window spread across the desktop.

It also adds visual feedback for Codex chats, so I can see when a chat has finished. If I want audio feedback, it can
play a jingle, and I can replace that jingle with any audio file on my computer.

## Why This Matters

The main goals are simple:

1. Use fewer clicks to get work done.
2. Make skills, documents, folders, and project setups reusable.
3. Reduce the number of windows and decisions I have to keep track of.

For my local and GitHub workflow, I would normally have several Finder windows, VS Code or a terminal, GitHub Desktop,
and github.com open at the same time. On my machine, that combination can use around 300 MB of memory, while GitDesk
handles most of the same workflow at around 60 MB.

It can also reduce AI usage costs because I do not need to spend as many model tasks on repetitive setup, file
management, reasoning, and execution. Based on the way I work, I think that could save around $20 to $100 or more per
week when individual tasks cost roughly $0.05 to $0.60. The exact savings will depend on how often someone uses those
workflows, but the point is that the app handles repeatable work locally instead of paying an AI to reason through it
again every time.

I put a lot of time and love into these apps because they have already been saving me time, disk space, memory, and a
lot of screen and mental clutter. I also think they are an easier way to show workflow ideas that products like
Flowith Canvas and Matrix could benefit from, because it is much easier to understand the value when someone can see
the workflow happen instead of reading a long list of individual features.

In short, GitDesk manages the project lifecycle, App Merger manages the workspace around it, and together they make it
faster and easier to go from an idea to a clean project, a working version, a GitHub build, and a public release.
