# Demo-Video-From-Site Skill — Implementation Plan

> **You are reading this in a fresh Claude session with no prior context.** Read this file first. Then drill into the linked docs based on what you're working on.

## What you're building

A Claude Code skill that takes a website URL + light guidance from a user and produces a fully-branded narrated demo video (mp4) of that site. The skill orchestrates every step: site exploration, storyboard drafting, voiceover generation, Playwright recording, audio/video mux, speed adjustment, branding overlay, intro/outro, and optional captions.

This skill lives at `~/.claude/skills/demo-video-from-site/`. It is **user-global** so it works across any project.

## Status — read this first

- **Planning phase only.** No scripts have been written in this folder yet. Only `docs/` exists.
- **A working reference implementation exists** in another repo. You will extract clean copies of its scripts and parameterize them. See [REFERENCE.md](./REFERENCE.md) for exact paths and what each existing script does.
- **All major design questions have been answered by the user.** See [DESIGN-DECISIONS.md](./DESIGN-DECISIONS.md) — do not re-litigate these. Treat them as binding requirements.

## What's in this folder

```
docs/
├── PLAN.md                 ← you are here
├── CONTEXT.md              background: what we built, why this skill exists
├── REFERENCE.md            paths to existing implementation; what to extract
├── DESIGN-DECISIONS.md     locked-in choices (do not re-debate)
├── ARCHITECTURE.md         skill folder layout + responsibilities
├── SCHEMAS.md              YAML schemas + action grammar for beats
├── SKILL-MD-OUTLINE.md     what to write in SKILL.md (the entry point Claude loads)
├── GOTCHAS.md              known issues, workarounds, non-obvious pitfalls
└── PHASE-A-TASKS.md        concrete checklist for the first build session
```

Read them in this order: `CONTEXT.md` → `DESIGN-DECISIONS.md` → `REFERENCE.md` → `ARCHITECTURE.md` → `PHASE-A-TASKS.md`. The other three (`SCHEMAS.md`, `SKILL-MD-OUTLINE.md`, `GOTCHAS.md`) are reference material — open as needed.

## End-to-end workflow this skill must produce

When a user invokes the skill (e.g. *"create a demo video of `https://app.example.com`"*), Claude must:

1. **Interview** the user — collect target URL, demo intent notes, audience, tone, length target, branding inputs, login info if any.
2. **Explore the site** — using Playwright MCP, navigate key pages, screenshot, read DOM.
3. **Draft storyboard.yaml** — 15–30 beats, each = one camera action + 1–3 sentences narration.
4. **Review with user in plain English** — present the flow as numbered beats with timestamps and narration quotes. Accept natural-language feedback ("skip beat 7, make beat 3 longer, add a mention of pricing"). Iterate until approved.
5. **Generate assets** — render Carver-style branded badge from logo, render intro/outro slides, generate PDF wrappers if any beat opens a PDF.
6. **Generate TTS** — run `scripts/render_voiceover.py` (OpenAI `gpt-4o-mini-tts`, voice `cedar` default).
7. **Record video** — run `scripts/record_demo.py` with Playwright, executing each beat's action and holding for `action_ms + PRE_MS + tts_ms + POST_MS`.
8. **Mux** — run `scripts/mux_demo.py` to align audio under video.
9. **Speed** — run `scripts/speed_video.py` (default 1.2x).
10. **Brand** — run `scripts/brand_video.py` to overlay badge + waveform + intro/outro + captions.
11. **Verify** — extract spot-check frames at key timestamps, report final duration + file size to user.

Every step writes named artifacts to a working directory so re-runs are cheap (e.g., if only narration tone needs adjusting, regenerate just the affected TTS clips and remux — don't re-record).

## Phased delivery

**Phase A — MVP (target: 1 build session of ~4 hours focused work).** Working skill end-to-end for sites without login or PDFs. Produces the same final video we already shipped, reproducibly. Detailed task list in [PHASE-A-TASKS.md](./PHASE-A-TASKS.md).

**Phase B — Full feature set (target: half-day).** Intro/outro slides, captions, login pre-session, PDF wrapper auto-generation, recipes library.

**Phase C — Polish (no target date).** Multi-provider TTS, richer site-adaptation recipes, better failure recovery.

Phase A is the priority. Phases B and C are not blockers for shipping.

## Defaults you can ship with

| Setting | Default |
|---|---|
| TTS provider + model | OpenAI `gpt-4o-mini-tts` |
| Voice | `cedar` (calm authoritative narration; `marin` is the brighter alternative) |
| Target video length | 5 minutes |
| Speed multiplier | 1.2x (so raw narration content ≈ 6 min) |
| Pre-narration buffer | 400 ms |
| Post-narration buffer | 700 ms |
| Badge size | 120 px |
| Badge position | bottom-left, 30 px from left, 36 px from bottom |
| Waveform | 200 × 36 px, lime, `mode=p2p`, `scale=sqrt` |
| Recording viewport | 1440 × 900 |
| Recording framerate | 25 fps |
| Output codec | h264 + AAC (`-crf 20 -preset medium`, `-b:a 192k`) |

## Refuse-to-proceed conditions

The skill must refuse to start generation if the user provides neither demo intent notes nor a logo. Generic demos with default branding produce bad demos — don't ship those silently. Ask the user to provide more guidance.

## Testing strategy

The reference implementation is the **Halyard Pay / Mastercard SPME demo** at `~/work/scribble/code/repos/carver/policy-diffs/credio-policies/dist/`. After Phase A is built, the skill must be able to reproduce that demo end-to-end given only:

- Target URL: `http://localhost:8080/index.html`
- Branding: Carver wordmark, ink `#101828`, lime `#bae424`
- Intent notes: "Show how an AI agent reviews five Mastercard SPME releases (2022–2025), proposes corresponding updates to Halyard Pay policies. Include the timeline, two verified change examples (§7.2 and §2.2.3), and one low-confidence example with extraction warning (§8.6.5)."

The example storyboard + branding YAMLs for this demo will live in `examples/halyard-spme/` and serve as the canonical reference.

## How to start (after reading the docs)

1. Read `CONTEXT.md` for background on what was already built.
2. Read `DESIGN-DECISIONS.md` to internalize the locked-in choices.
3. Read `REFERENCE.md` to learn the exact paths of the existing scripts you'll extract from.
4. Read `ARCHITECTURE.md` for the target folder layout.
5. Open `PHASE-A-TASKS.md` and start working through the checklist.
6. Reference `SCHEMAS.md`, `SKILL-MD-OUTLINE.md`, and `GOTCHAS.md` as you go.

When you finish Phase A, verify by running the skill against the Halyard demo (see Testing Strategy above) and confirming the output matches `~/work/scribble/code/repos/carver/policy-diffs/credio-policies/dist/demo-video.mp4` qualitatively.

## What the user wants you to do in the first build session

Build Phase A. Do not try to build Phase B in the same session. After Phase A is testable and produces the reference demo, stop and check in with the user.
