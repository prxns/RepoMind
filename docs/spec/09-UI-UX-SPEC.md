# RepoMind — UI/UX Specification

## Design direction
RepoMind is a **developer tool**, not an AI marketing website.

Do NOT use:
- purple/blue gradient backgrounds
- oversized hero typography
- floating glowing blobs
- excessive rounded cards
- glassmorphism
- fake AI sparkles everywhere
- generic “Unlock the future of AI” copy
- stock illustrations
- animated noise for decoration

## Visual character
Aim for the feel of a serious engineering product:
- neutral/light background with dark text OR a restrained dark developer-tool theme
- one restrained accent color
- thin borders
- compact spacing
- modest corner radii
- strong typography hierarchy
- monospace for file paths/code/technical metadata
- subtle hover/focus states
- no unnecessary animation

Reference mental models: GitHub, Linear, Vercel dashboard, modern IDE panels — but do not clone their branding.

## Main application layout
Desktop:
```text
┌────────────────────────────────────────────────────────────┐
│ RepoMind   owner/repository · branch          Status / menu │
├───────────────┬────────────────────────────────────────────┤
│ Conversations │                                              │
│               │  Question composer                           │
│  New question │  ─────────────────────────────────────────  │
│  Previous ... │                                              │
│               │  Answer                                      │
│               │  text...                                     │
│               │                                              │
│               │  Sources                                     │
│               │  file.py  L24–47                             │
│               │                                              │
└───────────────┴────────────────────────────────────────────┘
```

## Onboarding screen
Simple centered form:
- RepoMind wordmark
- “Understand a repository.”
- GitHub repository URL field
- branch/ref optional field
- primary action “Index repository”
- short note explaining what is indexed and what is not

No marketing hero section.

## Ingestion screen
Show:
- repository name
- branch/ref
- progress bar
- current stage
- counters: files / chunks
- errors if any

Use a compact status panel rather than a giant animated loader.

## Query screen
Answer layout:
- question at top
- answer in readable prose
- inline citation markers
- source list beneath answer
- expand source into code/text excerpt
- optional “retrieval details” accordion in debug/developer mode

## Empty state
Use useful prompts:
> “Try: Where is authentication implemented?”
> “Try: What calls the payment service?”
> “Try: Which tests cover user registration?”

## Typography
Use a modern sans-serif system font stack. Use monospace only for code, repository paths, hashes, and metrics.

## Accessibility
- keyboard navigation
- visible focus ring
- semantic controls
- button labels that describe actions
- no information conveyed by color alone
- responsive layout

## Copy style
Plain, technical, specific.
Bad: “Ask our AI anything about your codebase.”
Good: “Ask a question about this repository.”
Bad: “AI magic in seconds.”
Good: “Indexing files and building the search index.”
