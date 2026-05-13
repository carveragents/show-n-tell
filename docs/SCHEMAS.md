# YAML schemas + action grammar

This doc defines the three YAML files that drive every demo, plus the complete action grammar Claude can use when authoring a storyboard.

---

## 1. `storyboard.yaml`

The list of beats Claude drafts and the user approves. **Claude writes this file; the user never edits it directly.**

```yaml
# storyboard.yaml
# A beat is one camera action + one narration block. Each beat plays for:
#   action_ms (measured at record time) + 400ms + tts_duration_ms + 700ms
# Total runtime = sum of all beat durations.

beats:
  - id: 01_hero
    narration: |
      Welcome to Acme Cloud — a serverless deployment platform built for small
      teams who want zero-config production deploys.
    action:
      type: goto
      url: "{{ base_url }}/"

  - id: 02_features
    narration: |
      Three core capabilities power the platform: zero-config deploys, automatic
      SSL provisioning, and real-time logs piped directly to your terminal.
    action:
      type: scroll_into_view
      selector: ".features-grid"

  - id: 03_dashboard
    narration: |
      Clicking into the dashboard, every project shows a live activity feed —
      deploys, function invocations, and error rates updating in real time.
    action:
      type: goto
      url: "{{ base_url }}/dashboard"
```

### Beat fields

| Field | Required | Notes |
|---|---|---|
| `id` | yes | Stable identifier (snake_case, prefix with index for ordering). Used as TTS filename. |
| `narration` | yes | The spoken text. 1–3 sentences. Will be sent to TTS verbatim. |
| `action` | yes | See action grammar below. |
| `post_buffer_ms` | no | Override default 700ms POST_NARRATION_MS for this beat. |
| `pre_buffer_ms` | no | Override default 400ms PRE_NARRATION_MS for this beat. |

### Top-level `pdfs:` (optional, Phase B)

If any beat needs to display a PDF page, declare the source PDFs at the top of `storyboard.yaml`. The recorder runs a pre-flight step that downloads each PDF, rasterizes the requested page via `pymupdf`, and renders an HTML wrapper (`recipes/inline_pdf.html.j2`) that a `goto_pdf` beat can open via `file://` — this sidesteps Chromium's native PDF download behavior (see GOTCHAS #4).

```yaml
pdfs:
  - id: spme_2024_09_p60          # stable slug, used as filename + action ref
    source: "{{ base_url }}/sources/2024-09.pdf"   # local path or http(s) URL
    page: 60                       # 1-indexed
    citation: "SPME §6.2.2"        # optional, shown in wrapper toolbar
```

| Field | Required | Notes |
|---|---|---|
| `id` | yes | Stable slug. One id per (pdf × page). Used in `goto_pdf` action and as filename. |
| `source` | yes | Local path or `http(s)://` URL. Supports `{{ base_url }}` and `${ENV_VAR}` interpolation. |
| `page` | yes | 1-indexed page number to rasterize. |
| `citation` | no | Free-text label shown in the wrapper's toolbar (e.g. `"SPME §6.2.2"`). |

Pre-flight is idempotent: if `<working_dir>/_assets/pdf_wrappers/<id>_p<page>.html` already exists, that entry is skipped.

### Narration constraints (must enforce when drafting)

1. **Every factual claim in the narration must be verifiable on screen at this beat's frame.** If you say "five releases", "5" must be visible in the rendered page. No invented numbers.
2. **Initialisms** that should be read letter-by-letter (e.g., SPME, KYB, API) should be written with hyphens: `S-P-M-E`, `K-Y-B`, `A-P-I`. The TTS prompt enforces this.
3. **Length** of narration should match the beat's visual content. A scroll-into-view beat typically gets 8–18 seconds of narration. A click-and-show beat gets 6–12 seconds.
4. **Tone** must match `branding.yaml`'s `voice.tone` field (explanatory / sales / technical / casual).

---

## 2. `branding.yaml`

Per-brand config. Reusable across multiple demos from the same brand.

```yaml
# branding.yaml
brand:
  name: "Acme Cloud"
  tagline: "Serverless deploys for small teams"   # used on intro slide
  cta:                                              # used on outro
    text: "Try it free"
    url: "https://acmecloud.example.com"
  social:                                           # optional, outro footer
    twitter: "@acmecloud"

logo:
  path: "./logo.png"           # local file in the working dir, or downloaded
  source_url: "https://acmecloud.example.com/logo.png"   # optional, for re-download

colors:
  ink: "#101828"               # dark base — badge background
  ink_deep: "#0c1322"          # inner gradient stop (slightly darker)
  accent: "#bae424"            # ring border, waveform, pulse rings
  cream: "#fbf7f3"             # logo recolor, text on dark

voice:
  provider: openai
  model: "gpt-4o-mini-tts"
  voice: cedar                 # cedar | marin (per OpenAI's natural-narration recommendations)
  tone: "explanatory"          # explanatory | sales | technical | casual
  instructions: |
    Read calmly and clearly, like a confident product walkthrough narrator.
    Pace around 140 words per minute. Treat hyphenated initialisms like
    A-P-I letter by letter. Leave natural breaths between sentences.

recording_css: |
  /* Optional CSS injected at recording time only. */
  /* Used for sticky-header tricks, etc. */
  /* Leave empty if no site adaptation needed. */
```

### Caption style (Phase B; only relevant if `features.captions.enabled` is true)

```yaml
captions:
  font_size: 10           # libass units, default 10
```

`font_size` is in libass units against a default `PlayResY` of 288. On a 900-tall video the rendered text is roughly `font_size × 3.1` px. The default of 10 renders ~31px (~3.5% of the video height — typical professional subtitle size). Increase for emphasis (e.g. 14 → ~43px), decrease for a tighter look (e.g. 8 → ~25px).

Outline width (1) and bottom margin (30) are not exposed — they're sane regardless of the chosen font size.

### Color rules

- All four colors are required if a logo + dark badge is desired.
- If a brand has a *light* badge style, set `ink` to a light color and `cream` to the contrast color. The PIL renderer doesn't care which is which — it just uses ink for the gradient and cream for the logo fill.

---

## 3. `demo_config.yaml`

Per-demo config: where the site is, what the output is, login if any.

```yaml
# demo_config.yaml
site:
  base_url: "http://localhost:8080"
  # OR for live: "https://app.acmecloud.example.com"

session:
  pre_session: []              # see Login flow below

output:
  filename: "acme-demo.mp4"
  working_dir: "~/demo-videos/acme-2026-05-12"
  speed_multiplier: 1.2        # 1.0 = no speed-up
  target_duration_seconds: 300 # 5min target; informational only, used to flag if storyboard runtime is way off

features:
  intro_slide: true
  outro_slide: true
  captions:
    enabled: false             # default off
    mode: "burned"             # burned | srt-sidecar
  crossfade_seconds: 0.5       # 0 disables; up to 2.0
  brand_overlay: true          # badge + waveform

recording:
  viewport: { width: 1440, height: 900 }
  framerate: 25
  pre_narration_ms: 400
  post_narration_ms: 700
```

### `features.crossfade_seconds` (number, default `0.5`, range `0`–`2.0`)

Controls the duration of the audio + video cross-dissolve at the intro→main and main→outro seams. `0` disables the dissolve and uses the faster `-c copy` concat path (no re-encode). Values up to `2.0` are accepted; longer dissolves are refused because they eat too much intro/outro content. The dissolve uses ffmpeg's `xfade=transition=fade` (video) and `acrossfade=c1=tri:c2=tri` (audio). Crossfading shortens the final video duration by `(N-1) * crossfade_seconds` seconds.

### Login flow (Phase B)

```yaml
session:
  pre_session:
    - { type: goto, url: "{{ base_url }}/login" }
    - { type: fill, selector: "input[name=email]",    value: "${ACME_DEMO_EMAIL}" }
    - { type: fill, selector: "input[name=password]", value: "${ACME_DEMO_PASSWORD}" }
    - { type: click, selector: "button[type=submit]" }
    - { type: wait_for_url, contains: "/dashboard" }
```

Env vars referenced via `${NAME}` are resolved from the user's shell environment (or a `.env` file in the working dir). The skill loads `.env` automatically if present.

The pre-session runs once on the Playwright context before recording starts. The same context carries cookies / localStorage through all subsequent beats.

### `session.storage_state` (Phase B+, for OAuth / SSO / magic-link auth)

When the target site authenticates via OAuth, SSO, magic-link, or passkey
— flows that can't be reliably scripted via `pre_session` — pre-capture an
authenticated Playwright session and point the recorder at it.

```yaml
session:
  storage_state: "./auth.json"   # path to a Playwright storage_state JSON
  pre_session: []                # optional, runs AFTER storage_state loads
```

| Field | Required | Notes |
|---|---|---|
| `storage_state` | no | Path to a Playwright `storage_state.json`. Loaded via `browser.new_context(storage_state=...)` before pre_session. Relative paths resolve against `output.working_dir`. `~` is expanded. |

**Capture flow.** Use the bundled helper to capture a session whose browser
context matches the recorder's:

```bash
uv run helpers/capture_auth.py https://target.example.com/ --out ./auth.json
```

A headed Chromium opens, you log in interactively (handles OAuth, 2FA,
captchas — anything), and when you close the window the helper writes
`auth.json` with mode 0600. Add `session.storage_state: "./auth.json"` to
your `demo_config.yaml` and you're done.

**Re-capturing.** Sessions expire. When the demo starts recording you on a
login page, re-run `capture_auth.py`.

**Viewport match.** `capture_auth.py` and `helpers/explore_page.py` both
default to viewport 1440x900 (the recorder default). If you customize
`recording.viewport`, pass the same size via `--viewport WxH` to BOTH —
some sites invalidate sessions when the viewport changes between capture,
explore, and record.

**Security.** `auth.json` contains live session tokens. Never commit it.
The `examples/oauth-storage-state/` template includes a `.gitignore`.

**Combining with `pre_session`.** When both are set, `storage_state` loads
first into the context, then `pre_session` runs against that authenticated
context — useful for "OAuth-auth then navigate to the dashboard" demos.

---

## Action grammar

Every beat has exactly one `action`. The supported types:

### `goto`

Navigate to a URL. Waits for `networkidle`.

```yaml
action:
  type: goto
  url: "{{ base_url }}/some/path"
```

### `goto_and_scroll`

Navigate + smooth-scroll an element into view in a single beat.

```yaml
action:
  type: goto_and_scroll
  url: "{{ base_url }}/changes/abc.html"
  selector: ".extraction-warning"
```

### `scroll_into_view`

Smooth-scroll an element into view, respecting `scroll-margin-top`.

```yaml
action:
  type: scroll_into_view
  selector: ".features-grid"
```

### `scroll_y`

Scroll to absolute Y position (fallback when no good selector exists).

```yaml
action:
  type: scroll_y
  y: 900
  duration_ms: 1500    # optional
```

### `hover`

Hover over an element. Useful for showing tooltips, hovered states, or visually emphasizing UI.

```yaml
action:
  type: hover
  selector: ".timeline-card .severity-bar"
```

### `click`

Click an element. Optionally smooth-scroll a target after click.

```yaml
action:
  type: click
  selector: ".tabs a[href='#redline']"
  then_scroll: "#redline"      # optional
```

### `fill` (Phase B — primarily for login pre-sessions)

Type a value into a form input. Used mainly inside `session.pre_session`,
but legal in regular beats too (e.g. form-fill demos).

```yaml
action:
  type: fill
  selector: "input[name=email]"
  value: "demo@example.com"    # or "${ENV_VAR}"
```

`${ENV_VAR}` substitution applies to **all** actions inside
`session.pre_session` — not just `fill` — so URLs and selectors can also
reference env vars when useful. In regular beats, only `{{ base_url }}`
template interpolation runs; env-var expansion is reserved for
pre_session so credentials don't bleed into the storyboard.

Credential hygiene: when the recorder logs a `fill` step that ran during
pre_session, `value` is masked to `***` in stdout.

### `goto_pdf` (Phase B — for displaying a PDF page)

Open the auto-generated HTML wrapper around a rasterized PDF page. The pdf must be declared in the top-level `pdfs:` block (see above); pre-flight handles fetching and rendering.

```yaml
action:
  type: goto_pdf
  pdf_id: spme_2024_09_p60     # must match an entry in storyboard's `pdfs:`
```

The recorder resolves the wrapper file at `<working_dir>/_assets/pdf_wrappers/<pdf_id>_p<page>.html` and navigates to it via `file://`. The wrapper shows a dark-toolbar PDF-viewer-style chrome with the requested page rendered as a PNG at 2x DPI (~144 dpi), max 900px wide.

### `wait_for_url`

Wait until URL matches a pattern. Used after clicks that trigger navigation.

```yaml
action:
  type: wait_for_url
  contains: "/dashboard"
```

### `wait_for_selector`

Wait until an element appears (lazy-loaded content, modal open, etc.).

```yaml
action:
  type: wait_for_selector
  selector: ".chart-loaded"
  timeout_ms: 5000     # optional, default 5000
```

---

## Action execution timing

The recorder measures wall-clock time for each action and writes it to `timings.json`. The skill then uses those measurements to build a perfectly synced audio track.

```
Per beat:
  t_start
  ↓
  execute action               ← action_ms measured here
  ↓
  wait PRE_NARRATION_MS        ← 400ms default
  ↓
  wait tts_duration_ms         ← TTS plays during this window
  ↓
  wait POST_NARRATION_MS       ← 700ms default
  ↓
  t_end

Per audio track segment:
  silence(action_ms + PRE_NARRATION_MS)
  + tts wav for this beat
  + silence(POST_NARRATION_MS)
```

Audio track + video track land at exactly the same total duration as long as the recorder measured action_ms correctly.

## Variable interpolation

`{{ base_url }}` in URLs is substituted from `demo_config.yaml`'s `site.base_url` at runtime.

`${ENV_VAR}` in any string field is substituted from shell environment / `.env`.
