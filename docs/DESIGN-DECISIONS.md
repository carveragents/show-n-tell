# Design decisions — locked in, do not re-debate

The user has answered all major design questions. Treat these as binding requirements.

## 1. Storyboard authoring: Claude drafts, user reviews in plain English

Claude is responsible for producing a complete storyboard draft from the user's intent notes + site exploration. The user does **not** edit YAML directly. Instead, Claude presents the storyboard as a numbered list in natural language and accepts conversational feedback ("skip beat 7", "make beat 3 longer", "mention pricing somewhere", "change the tone to more casual").

Claude is the technical author; the user is the editorial reviewer.

**Implication:** SKILL.md must specify exactly how to present the storyboard for review (format, what to include) and how to interpret natural-language feedback into YAML edits.

## 2. Install location: user-global at `~/.claude/skills/`

The skill is `~/.claude/skills/show-n-tell/`. It is reused across projects. It must not assume the cwd is any particular repo.

When running the skill, Claude creates a working directory **per demo** (e.g., `~/demo-videos/<demo-name>/`) for the storyboard, branding, generated TTS, recorded video, and final output. The skill folder itself stays clean — only scripts, templates, examples, and the SKILL.md live there.

## 3. Branding scope: badge + waveform + intro/outro + captions

The skill must support all four:

- **Bottom-left circular badge** with logo, gradient background, ring border, halo glow, pulse rings (Phase A)
- **Audio waveform** below the badge, audio-reactive via ffmpeg `showwaves` (Phase A)
- **Intro slide** (3–5 s) — logo + title + tagline + gradient bg (Phase B)
- **Outro/end card** (4–6 s) — logo + CTA + URL + optional social handles (Phase B)
- **Captions** — generated from storyboard narration + per-beat timings, output as burned-in or SRT sidecar (Phase B; default off)

Each is independently toggleable in `demo_config.yaml`.

## 4. The skill is self-contained

Never import code from sibling projects at runtime. Every script and asset the pipeline needs lives in this repo. A fresh `git clone` plus `uv sync` is the entire install; nothing implicit.

This is why the skill stays portable — it can ship as its own repo, no dependency on whatever project the original demo was built from.

## 5. Login flows: must be supported (Phase B)

Some target sites require authentication before the demo content is reachable. The skill must support a `pre_session` config that runs auth steps once on the Playwright context before recording begins. Credentials come from `.env` (or shell env vars), never hardcoded.

Example session config:

```yaml
session:
  pre_session:
    - { type: goto, url: "{{ base_url }}/login" }
    - { type: fill, selector: "input[name=email]", value: "${DEMO_EMAIL}" }
    - { type: fill, selector: "input[name=password]", value: "${DEMO_PASSWORD}" }
    - { type: click, selector: "button[type=submit]" }
    - { type: wait_for_url, contains: "/dashboard" }
```

After pre-session completes, the recording proceeds normally using the same authenticated context. Persistent storage state (cookies, localStorage) is preserved across all beats.

Phase A can skip this — but the recorder's architecture should be designed to accept a pre-session block without requiring a rewrite later.

## 6. TTS provider: OpenAI only for v1

`gpt-4o-mini-tts` is the model. `cedar` is the default voice. `marin` is the documented alternative. No other providers (ElevenLabs, etc.) for now — design the TTS module so a provider abstraction is easy to add later, but don't build it.

## 7. Site adaptations: Claude decides on demand

The skill does **not** ship an exhaustive catalog of site-specific workarounds. Instead, Claude inspects each target site during the exploration phase, identifies issues (sticky-header layout problems, PDF deep-links that won't render in headless mode, modal dialogs, lazy content, etc.), and applies recipes from `recipes/` as needed.

The `recipes/` folder ships a small set of common adaptations:

- `sticky_header.css.j2` — Jinja-templated CSS for pinning headers (used when scrolling into long-form content)
- `inline_pdf.html.j2` — HTML viewer wrapper for PDFs rendered via pymupdf
- `login_form_fill.yaml` — reference fragment for pre-session auth blocks

Claude composes these per-demo. The recipe library is opt-in, not auto-applied.

## 8. Defaults

| Setting | Default |
|---|---|
| Target video length | 5 minutes |
| Speed multiplier | 1.2x |
| Pre-narration buffer | 400 ms |
| Post-narration buffer | 700 ms |
| Recording viewport | 1440 × 900 |
| Recording framerate | 25 fps |
| Badge size | 120 px |
| Badge position | bottom-left, 30 px from left, 36 px from bottom |
| Waveform | 200 × 36 px, mode `p2p`, scale `sqrt`, color matches accent |

## 9. Refuse-to-proceed conditions

Refuse to start generation if the user provides neither intent notes nor a logo. Generic demos with default branding produce bad demos — surface this to the user, ask for more guidance, do not silently produce a generic video.

## 10. Verification before claiming success

After producing the final mp4, extract ≥3 spot-check frames at key moments (intro, mid-demo, outro), inspect them, and report visible state to the user. Do not claim "demo is ready" without checking what's actually in the frames. This applies especially to:

- Whether the brand badge appears in expected position
- Whether section headers / sticky elements render correctly
- Whether narration's claims match what's on screen at the relevant beat

If a mismatch is detected, fix it before reporting completion.
