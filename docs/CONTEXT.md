# Background: how this skill came to exist

## The origin demo

The user (a product engineer at Scribble building Carver Agents — an AI agent platform for compliance/risk at payment processors) was running a Phase 1 POC: an AI pipeline that detects changes between consecutive Mastercard SPME publications, classifies their materiality, and proposes corresponding updates to a hypothetical processor's internal compliance policies ("Halyard Pay" — fictional, synthetic baseline).

The POC ships as a static site (`credio-policies/dist/`) that lets reviewers browse the changes interactively. The user wanted a self-contained narrated video walkthrough for external prospects.

Over the course of one session we built, end-to-end:

1. A 28-beat storyboard with hand-crafted narration aligned to specific scroll positions and visual moments
2. A Playwright-based recording pipeline that times every camera action precisely
3. An OpenAI TTS pipeline (`gpt-4o-mini-tts` voice `cedar`) for the narration
4. An audio/video mux pipeline that locks audio to video using per-beat measured action times
5. A 1.2x speed-up post-process to land at 5 min
6. A Loom-style branded overlay with:
   - Bottom-left circular badge containing the actual Carver Agents wordmark (downloaded from carveragents.ai)
   - Dark ink radial gradient background, lime ring border, halo glow, two phase-staggered pulse rings
   - Audio-reactive lime waveform below the badge driven by ffmpeg's `showwaves` filter

The final video is at `~/work/scribble/code/repos/carver/policy-diffs/credio-policies/dist/demo-video.mp4` — 5:09, 28.8 MB, h264 + AAC.

## Why turn this into a skill

The pipeline is highly reusable. What's project-specific is the storyboard (which pages, which selectors, what to say) and a few site-specific adaptations (sticky-header CSS injection for change-page H1s, PDF rendering wrapper, NODE_OPTIONS unset). Everything else — TTS, recording timing, audio mux, speed adjustment, brand overlay, etc. — is fully reusable.

The user wants to be able to point at **any website**, provide light guidance ("demo my dashboard, click into reports, show the filter UX"), and get a polished video out. The skill should drive that workflow conversationally.

## What's "Loom-style" mean here

Loom is a screen-recording tool that overlays a small circular webcam bubble in the corner of recordings. The user wanted the badge to feel like that — a small persistent brand marker that signals "this is a real product demo, presented by [brand]," with subtle motion to feel alive. We don't have a webcam; the badge shows the brand wordmark instead, with continuous pulse rings (signaling "speaking") and an audio-reactive waveform (showing actual voice activity).

## Key design tensions resolved during the build

1. **Section-header visibility vs diff content visibility.** Change-detail pages have a long header (title + materiality badge + sources + callout + tabs) before the side-by-side diff content. Scrolling far enough to show diffs pushed the header out of frame, losing context. Solution: inject a CSS rule at recording time that pins `.change-header` sticky-to-top. Real users on the deployed site don't get the sticky behavior — it's recording-only.

2. **PDF deep-links breaking in headless Chromium.** Real users clicking a PDF link get inline rendering via the browser's built-in viewer. Headless Chromium triggers a download instead. Solution: pre-render the PDF page as a PNG via pymupdf and serve it through a small HTML viewer wrapper styled to look like a PDF viewer. Recording navigates to the wrapper; production users still get the real PDF.

3. **Narration alignment with on-screen content.** The user explicitly wants the voiceover to only quote numbers/facts that are visible on screen at that moment. No "the agent flagged 199 changes" if the user can only see one card's stats. This is a non-negotiable constraint — when drafting any storyboard, every claim in the narration must be visible on screen at the moment it's spoken.

4. **Narration vs visual matching.** Beat 16 originally clicked a tab but narrated the wrong tab. Beat 22 narrated a value change that wasn't visible in the YAML diff. These mismatches were caught by frame inspection and corrected. The skill must do the same: after recording, extract frames at key beats and verify the narration matches what's on screen.

5. **Continuous pulse vs audio-synced glow.** Audio-synced glow on the badge requires per-frame composition driven by amplitude analysis — high complexity, diminishing return when the waveform already shows audio activity. Resolved: continuous pulse rings on the badge (always animating, 2s loop), waveform handles audio reactivity. Don't over-build sync.

## Who the user is

- Senior product engineer, builds full-stack products
- Has deep React/Go background, comfortable with config-driven workflows
- Wants the skill to be **opinionated** about defaults but configurable when needed
- Prefers terse, direct communication; no flattery or filler
- Wants verification commands run (frame extraction, duration checks) rather than hand-waved success claims
- Values testability and reproducibility — the skill should produce identical output given identical inputs

## What "good output" looks like

The Halyard Pay demo at the path above is the gold standard. Specifically:

- Bottom-left brand badge persistent through every frame
- Section headers always visible during diff content scrolls
- Narration says only what's visible on screen
- Pacing feels natural (140 wpm raw, 168 wpm at 1.2x — still listenable)
- Intro feels brief, not bloated; outro feels intentional, not abrupt
- Audio waveform reacts visibly to voice activity
- Total runtime within 30s of the user's target length

Any new demo produced by the skill should hit those marks.
