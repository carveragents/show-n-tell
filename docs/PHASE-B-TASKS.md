# Phase B — concrete task checklist

Goal: extend the working Phase A pipeline with the four features deferred by the user: **intro/outro slides, captions, login pre-session, PDF wrapper auto-gen**. Plus a small recipe library.

**Estimated effort: ~5–6 hours of focused work.** Tasks 1–4 are independent and can be parallelized; Task 5 depends on 3 & 4; Tasks 6–8 close it out.

Phase A is the working baseline — don't break it. Every Phase B feature is gated by a flag in `demo_config.yaml` so demos that don't need it still work unchanged.

---

## Pre-work (5 min)

- [x] Confirm Phase A still passes end-to-end against the Halyard reference. Run the full pipeline; final mp4 should still come out ~5:09.
- [x] Read `docs/SCHEMAS.md` Phase B sections (action grammar `fill` / `wait_for_url`, `session.pre_session`, `features.intro_slide / outro_slide / captions`).
- [x] Verify `pymupdf` and `jinja2` install cleanly under `uv run --with`.

---

## Task 1 — PDF wrapper auto-gen (75 min)

The reference demo's PDF beat opens a hand-crafted HTML wrapper at `dist/_recording_assets/pdf_view_2024-09_p60.html` showing a pymupdf-rendered PNG of page 60. Phase B automates this so Claude can declare PDF beats and have the wrapper generated at prep time.

**Source material (reference):**
- HTML template: `~/work/scribble/code/repos/carver/policy-diffs/credio-policies/dist/_recording_assets/pdf_view_2024-09_p60.html`
- Sample PNG: `…/spme_2024-09_p60.png`

**Build:**

- [x] `recipes/inline_pdf.html.j2` — Jinja template, parameterized on `{filename, citation, page, total, page_image}`. Match the styling of the reference wrapper (dark `#525659` body, `#323639` toolbar, white card with shadow, max-width 900px).

- [x] `helpers/pdf_wrapper.py`:
  ```bash
  uv run helpers/pdf_wrapper.py \
    --working-dir <path> \
    --pdf-id spme_2024_09_p60 \
    --pdf-source <local-path-or-url> \
    --page 60 \
    [--citation "SPME §6.2.2"]
  ```
  - Downloads the PDF if `--pdf-source` is an http(s) URL; caches in `<working_dir>/_assets/pdfs/<pdf-id>.pdf`.
  - Rasterizes the requested page via `pymupdf` at 2x DPI to `<working_dir>/_assets/pdf_pages/<pdf-id>_p<N>.png`.
  - Renders the Jinja template to `<working_dir>/_assets/pdf_wrappers/<pdf-id>_p<N>.html`.

- [x] **Storyboard schema addition** — at the top level of `storyboard.yaml`:
  ```yaml
  pdfs:
    - id: spme_2024_09_p60
      source: "{{ base_url }}/sources/2024-09.pdf"
      page: 60
      citation: "SPME §6.2.2"
  beats:
    ...
    - id: 13_change_pdf
      action: { type: goto_pdf, pdf_id: spme_2024_09_p60 }
      narration: "..."
  ```
  - SKILL.md workflow: when drafting, if a page needs a PDF, declare it in `pdfs:` and reference via `goto_pdf` action.
  - Pre-record step in `record_demo.py` (or a new orchestrator) iterates `pdfs:` and runs `helpers/pdf_wrapper.py` for each.

- [x] **Action grammar addition** in `scripts/record_demo.py`:
  - Add `goto_pdf` to `SUPPORTED_ACTIONS`.
  - In `execute_action`, resolve `pdf_id` → wrapper file path → `file://<absolute>` URL, then `page.goto`.

- [x] **Test:** add a PDF beat to a small example. Run pipeline. Verify the wrapper renders the right page, the wrapper page loads in headless Chromium without a download dialog (GOTCHAS #4), and the beat's frame shows the PDF content.

**Acceptance:** the existing Halyard beat 13 (`13_change_pdf`) reproduces the reference's PDF page without the hardcoded `_recording_assets/pdf_view_2024-09_p60.html` wrapper — purely from a `pdfs:` declaration in the storyboard.

---

## Task 2 — Login pre-session (45 min)

Phase A stubs pre-session with a "skipping in Phase A" warning. Phase B implements it.

**Build:**

- [x] In `scripts/record_demo.py`:
  - Add `fill` to `SUPPORTED_ACTIONS` and to `execute_action`:
    ```python
    elif t == "fill":
        page.locator(action["selector"]).first.fill(action["value"])
    ```
  - In `main()`, before executing each pre_session step, also call `expand_env` (in addition to the `interp_template` already happening) so `${ENV_VAR}` values resolve.
  - Replace the stub `run_pre_session` body with: iterate steps, call `execute_action` on each.

- [x] `recipes/login_form_fill.yaml` — reference fragment showing the canonical login pre-session shape (already documented in `docs/SCHEMAS.md` — just extract).

- [x] **Credentials hygiene** — `record_demo.py` must NOT log resolved `value` strings if the step is `fill` (mask them in stdout). Add `_sanitize_action_for_logging()`.

- [x] **Test:** spin up a tiny local Flask app with `/login` (POST email+password → set cookie → redirect to `/dashboard`). Set `DEMO_EMAIL` + `DEMO_PASSWORD` in `<working_dir>/.env`. Use a 3-beat storyboard that exercises post-login state. Verify the recording shows the dashboard, not the login wall.

**Acceptance:** a recorded demo of a site behind auth shows the authenticated content, with credentials never appearing in logs or in the storyboard.

---

## Task 3 — Intro / outro slides (60 min)

**Build `scripts/make_intro_outro.py`:**

- [x] CLI:
  ```bash
  uv run scripts/make_intro_outro.py --working-dir <path>
  ```
  - Reads `branding.yaml` (`brand.name`, `brand.tagline`, `brand.cta`, `brand.social`, `colors.*`, `logo.path`).
  - Reads `demo_config.yaml`'s `features.intro_slide` + `features.outro_slide` booleans + the recording viewport.

- [x] **Intro slide** (default 4s):
  - Dark ink gradient background (same gradient palette as the badge).
  - Centered: logo (large, recolored to cream), brand name (sans-serif, large), tagline (smaller, accent color or cream).
  - 1s fade-in + 2s hold + 1s fade-out feel (use ffmpeg fade filter or pre-render frames).

- [x] **Outro slide** (default 5s):
  - Same background palette as intro.
  - Centered: logo, CTA text, CTA URL (large), social handles row (small, below).

- [x] Render approach (choose one):
  - **Option A — PIL static + ffmpeg encode:** render two PNGs, encode each with `-loop 1 -t <duration> -i slide.png -c:v libx264 -t <duration> -pix_fmt yuv420p ... -vf "fade=t=in:st=0:d=0.8,fade=t=out:st=<d-0.8>:d=0.8"`.
  - **Option B — PIL frame sequence:** render every frame with PIL, encode at recording framerate. Slower but more control (animated fade-in of subtitle text, etc.).
  - Start with Option A. Bump to B only if motion is unsatisfying.

- [x] Outputs: `<working_dir>/_intermediate/intro.mp4`, `<working_dir>/_intermediate/outro.mp4` matching recording viewport + framerate, with silent AAC audio (so concat doesn't need re-encode of the main track's audio).

- [x] **Test:** render against the Halyard branding. Inspect intro frame at t=2s: logo centered, "Carver Agents" name visible, tagline visible. Inspect outro at t=2s: CTA visible.

**Acceptance:** running this script in the halyard test working-dir produces an `intro.mp4` and `outro.mp4` that play cleanly when opened standalone.

---

## Task 4 — Captions / SRT (45 min)

**Build `scripts/make_captions.py`:**

- [x] CLI:
  ```bash
  uv run scripts/make_captions.py --working-dir <path>
  ```
  - Reads `_voiceover/manifest.json` (narration text + chars) and `_voiceover/timings.json` (per-beat action_ms, tts_ms, pre/post buffers).
  - Reads `demo_config.yaml`'s `output.speed_multiplier`.

- [x] **SRT timing math:** for beat *i*, raw start = sum over prior beats of `(action_ms + pre_ms + tts_ms + post_ms)` + `action_ms_i + pre_ms_i`. Raw end = raw start + `tts_ms_i`. Apply `/ speed_multiplier` to both for the final-video timeline.

- [x] One SRT entry per beat. Don't try to word-split — keep it simple. Long narration produces a long single subtitle; that's acceptable for v1.

- [x] Output: `<working_dir>/_voiceover/captions.srt`.

- [x] **Test:** open `captions.srt` in QuickTime alongside the final mp4. First subtitle should appear when narration 1 starts (not at t=0; after the action_ms of beat 1). Last subtitle should end before the video does.

**Acceptance:** SRT entries align with the audible narration to within 200ms on at least 5 spot-check beats.

---

## Task 5 — Finalize: intro+outro concat + caption burn-in (45 min)

Phase A's `brand_video.py` handles badge + waveform only. Phase B adds a **new** finalize step that runs AFTER `brand_video.py`:

**Build `scripts/finalize_video.py`:**

- [x] CLI:
  ```bash
  uv run scripts/finalize_video.py \
    --working-dir <path> \
    --input <branded.mp4> \
    --output <final.mp4>
  ```

- [x] Reads `demo_config.yaml`'s `features.intro_slide`, `features.outro_slide`, `features.captions.enabled`, `features.captions.mode`.

- [x] **Intro/outro concat** (when enabled): ffmpeg `concat` filter with intro.mp4 + branded.mp4 + outro.mp4. Make sure all three have matching codecs/framerate/resolution/sample-rate — `make_intro_outro.py` must produce the same encoding profile as `brand_video.py`.

- [x] **Caption burn-in** (when `captions.mode == "burned"`): ffmpeg `subtitles=<srt>:force_style='FontName=...,FontSize=...,Outline=2'` filter. Apply AFTER intro/outro concat so caption timing offsets correctly account for the intro duration (or burn captions before concat and adjust SRT timings — pick one approach and document).

- [x] **Caption sidecar** (when `captions.mode == "srt-sidecar"`): copy SRT next to final mp4 as `<output>.mp4.srt` (e.g. `demo.mp4.srt`). No filter applied. Keeping the full video filename in the sidecar avoids stomping a sibling file that happens to share the basename (e.g. a pre-existing `demo.srt` from a different run).

- [x] **Default behavior** when all flags are off: copy the input mp4 through as-is (no re-encode).

- [x] **Test:** end-to-end run on Halyard with all three features enabled. Final mp4 should have intro slide → original demo → outro slide. Captions visible at the bottom of the demo section.

**Acceptance:** running the full Phase B pipeline against Halyard with `features: { intro_slide: true, outro_slide: true, captions: { enabled: true, mode: burned } }` produces a single mp4 with all three features present, ~5:09 + intro_duration + outro_duration in total.

---

## Task 6 — Site exploration helpers (optional, 30 min)

Claude already has the Playwright MCP tools and uses them directly during the exploration phase. A helper script is mostly redundant — keep this task only if there's a clear win.

**Possible scope** (defer to taste):

- [ ] `helpers/site_explorer.py`:
  ```bash
  uv run helpers/site_explorer.py --url <url> --snapshot-dir <path>
  ```
  Loads URL with the same recording viewport, screenshots above-the-fold, dumps a stable-selector summary (every element with `id` + every element with `data-testid` + first 50 elements with role).

- [x] If skipped, document that the skill workflow uses MCP directly for exploration.

**Recommendation:** skip this task. The MCP tools are sufficient. If you skip, mark this task done with a one-line note in SKILL.md.

**Resolution:** skipped per the recommendation. Phase 2 of SKILL.md already directs Claude to use the Playwright MCP tools (`mcp__plugin_playwright_playwright__*`) for exploration; no helper script was added.

---

## Task 7 — Phase B Halyard example update (30 min)

Extend `examples/halyard-spme/` to exercise Phase B features as the canonical reference:

- [x] Add `pdfs:` block to `storyboard.yaml`. Convert beat 13 (`13_change_pdf`) from a `goto` to a `goto_pdf` action referencing a declared PDF.
- [x] Add the original Mastercard PDF to the example (or instructions for downloading from archive.org).
- [x] Update `demo_config.yaml` to set `features.intro_slide: true`, `features.outro_slide: true`, `features.captions.enabled: true`.
- [x] Add `brand.tagline`, `brand.cta`, `brand.social` to `branding.yaml`.
- [x] **Build a separate example** for login: a 5-beat demo of a tiny Flask app, with `.env` template (env-var names only, no actual credentials).

**Acceptance:** running the Phase B halyard pipeline produces a video with intro, outro, captions, and a PDF beat that loads inline.

---

## Task 8 — SKILL.md + CLAUDE.md updates (30 min)

- [x] **SKILL.md** — phase 5 (asset prep): mention `pdf_wrapper.py` for PDF beats. Phase 6: mention `make_intro_outro.py`. Phase 7: mention `make_captions.py`. New phase 9.5 between brand and verify: `finalize_video.py`. Update phase 1 interview to actually collect login credentials when needed (currently warns "Phase B only").
- [x] **CLAUDE.md** — flip "Phase B isn't implemented yet" notes. Update the preserve-list with any new gotchas surfaced during the build (the existing GOTCHAS.md should also gain entries — add them as you encounter them).
- [x] **docs/PHASE-B-TASKS.md** (this file) — when finished, mark each task complete and add a closing note: what's left for Phase C.

---

## Phase B acceptance criteria

- [x] Phase A pipeline still produces an identical result when all Phase B flags are disabled.
- [x] PDF beats work without manual wrapper hand-crafting.
- [x] Login pre-session authenticates and the recording captures post-login state, with no credentials leaked to stdout or to checked-in YAML.
- [x] Intro and outro slides bracket the main demo cleanly (no codec/framerate stutter at the seams).
- [x] Captions burn in legibly (white text + dark outline) and align to audio within ~200ms.
- [x] SKILL.md no longer says "Phase B isn't implemented".

## Stop after Phase B

Phase C (multi-provider TTS, richer recipes, failure recovery) is out of scope for this build. After Phase B is testable and the Halyard example exercises all four features, stop and check in with the user.

---

## Phase B retrospective — complete 2026-05-12

Phase B shipped end-to-end on the date above. The Halyard reference now reproduces both the Phase A baseline (`halyard-demo.mp4`, ~5:09, badge + waveform only, all `features.*` off) and the Phase B canonical (`halyard-demo-phaseb.mp4`, ~5:18, intro + branded demo + burned captions + outro, PDF beat auto-wrapped) from the same `examples/halyard-spme/` inputs.

### Commits that landed each task

| Task | Commits |
| --- | --- |
| 1 — PDF wrapper auto-gen | `4545a45` + `f314d4c` |
| 2 — Login pre-session | `9e36fee` + `6cdacbd` |
| 3 — Intro / outro slides | `74dc1cd` + `cdecd5c` |
| 4 — Captions / SRT | `6f034f9` + `27f36b7` |
| 5 — Finalize video | `ab62957` + `277c326` |
| 6 — Site exploration helpers | skipped (per recommendation; MCP tools cover the use case) |
| 7 — Phase B Halyard example update | `4db30bc` |
| 8 — SKILL.md + CLAUDE.md updates | `7efe263` (+ `<this commit>` for the SHA fill-in) |

### What surfaced during the build (now captured)

- `docs/GOTCHAS.md` gained entries **#18–22** covering libass availability, `subtitles=` path escaping, `force_style` comma escaping, encoder profile consistency for `-c copy` concat, and credential expansion order + traceback hygiene.
- `CLAUDE.md`'s preserve-list mirrors those entries so future maintainers extracting from the working scripts don't re-derive them.

### Deferred to Phase C

- **Multi-provider TTS.** OpenAI is still the only backend. ElevenLabs / Cartesia / local Piper are candidates; the manifest format already abstracts the per-beat wav contract enough that the swap is one script.
- **Richer site-adaptation recipes.** Today: sticky-header + PDF wrapper. Wanted: modal-dismiss helper, lazy-content wait patterns, more login templates (OAuth click-through, magic-link, MFA bypass for test accounts).
- **Failure recovery.** A single failed beat currently invalidates the whole recording. Want: detect the failing beat, re-record just that beat at its segment of the timeline, splice into the existing webm. Non-trivial — Playwright's per-page recording mode complicates it.
- **Audio crossfade at intro/main/outro seams.** Today the seams are hard cuts on silent intro/outro audio tracks. Sub-second crossfades (`acrossfade`) would soften the transition and hide any tiny sample-rate drift if a user does customize one of the encoders.
