# demo-video-from-site

**Turn any website into a narrated, branded demo video in under 20 minutes.**

You tell Claude Code which site, what story to tell, and drop in a logo. It walks the site, drafts the narration, gets you to review in plain English, records the screen with a voiceover, and ships a finished mp4 with your brand badge, captions, and optional background music.

The output looks like a polished Loom-style product walkthrough — but faster to make, easier to update, and you can change the narration tone or branding without re-recording.

---

## What you'll need before starting

| | What | How to get it |
|---|---|---|
| 1. | **Claude Code** | https://claude.com/claude-code |
| 2. | **Homebrew** (Mac) | https://brew.sh |
| 3. | **`ffmpeg-full`** | `brew install ffmpeg-full` (the basic `ffmpeg` works, but `ffmpeg-full` includes caption rendering) |
| 4. | **`uv`** (Python runner) | `brew install uv` |
| 5. | **An OpenAI API key** | https://platform.openai.com/api-keys — for the AI narration voice; ~$0.10 per demo |
| 6. | **Google Chrome** (only if your site uses login) | https://www.google.com/chrome — needed for sites with Google OAuth, Microsoft SSO, etc. |
| 7. | **Your site's logo** | A `.png` file on your computer (or a public URL Claude can download) |

If you've never run Claude Code before: install it, sign in, then open a terminal in any folder and type `claude`. That starts the conversation interface.

---

## Installing the skill

Once Claude Code is running, install this skill into your global skills folder:

```bash
git clone https://github.com/<your-org>/demo-video-from-site \
  ~/.claude/skills/demo-video-from-site
```

That's the whole installation. The skill is now available across every Claude Code session, anywhere on your machine. You don't need to "activate" it — just describe what you want and Claude will pick it up.

The first time you make a demo for a logged-in site, you'll be prompted to run `playwright install chromium` (one command, one minute). Claude Code will tell you exactly when.

---

## Your first demo

Open Claude Code in any folder (the demo will save outside your project — doesn't matter where you start). Type:

> Let's create a demo video for the site I'm working on.

Claude will ask you for the things below. You can answer in plain English, all at once or one at a time.

### Things Claude will need from you (required)

1. **The URL** of the site you want to demo.
2. **What story you want to tell** — 1–3 sentences. What features matter most? What should the viewer walk away knowing? Examples: *"Show off the new dashboard's live activity feed and how the AI auto-categorizes uploads"* or *"It's a meal planning app — I want viewers to see how easy it is to add a dish, get suggestions for tonight, and plan a week of dinners."*
3. **Audience and tone** — Who's watching, what's the vibe? Examples: *"External customers, casual but friendly"* / *"Internal team, technical and dry"* / *"Investors, polished and confident."*
4. **A logo** — file path on your computer (Claude will copy it for you), or a public URL.
5. **Login type** — does the site need a login?
   - **No login** — skip
   - **Email/password I'd type in myself** — Claude scripts the login using credentials you put in an `.env` file (so they're never typed into chat)
   - **Google / Microsoft / SSO / magic link** — Claude opens a Chrome window, you log in once like a normal user, and the session is saved for the recording

That's it for mandatory. Claude will refuse to start without intent and a logo — generic demos are bad demos.

### Things you can adjust (optional)

If you skip these, Claude picks sensible defaults.

- **Length** — default is 5 minutes; ask for shorter if you want a sub-3-minute teaser.
- **Brand colors** — primary ink color + accent color, in hex (`#1f7472`). Skip and Claude infers them from your logo.
- **Voice** — `cedar` (calm, authoritative — good for product/B2B) or `marin` (brighter, warmer — good for consumer/casual). Default: `cedar`.
- **Captions** — burned into the video (good for social media autoplay) or shipped as a separate `.srt` sidecar file. Default: burned.
- **Intro / outro slides** — short branded splash at start and end. Default: both on.
- **Background music** — silent by default. Set a mood and Claude mixes a royalty-free track from a bundled library under the narration, automatically ducking the music whenever the narrator speaks. Available moods: `upbeat`, `warm`, `calm`, `playful`, `cinematic`, `tech`. Or point Claude at your own music file.

You don't need to know YAML or read any config files. Just tell Claude in conversation. *"Make it sound more casual," "make the music calmer," "swap the accent color to orange"* all work.

---

## What happens, step by step

Once Claude has your inputs:

1. **Explores the site.** Visits a handful of pages, takes screenshots, notes what's where. ~2 minutes.
2. **Drafts a storyboard.** A numbered list of 15–30 short "beats" — each beat is one camera move (click, scroll, hover) with one or two sentences of narration. Claude shows it to you in plain text. ~1 minute.
3. **You review.** Read the list, say what you want to change in plain English. *"Skip beat 7," "make beat 3 longer," "the tone is too formal."* Claude rewrites and re-presents. Repeat until you say "ship it." ~2–5 minutes.
4. **Generates narration audio.** Runs OpenAI's TTS on each beat. ~$0.10. ~2 minutes.
5. **Records the screen.** Drives a browser through the site at recording-quality, mics in your voiceover, captures the result. ~3–6 minutes (roughly real-time per beat).
6. **Polishes.** Adds the brand badge in the corner, a waveform animation, captions, optional intro/outro slides, optional background music. ~1 minute.
7. **Verifies.** Pulls 3+ frames from the finished video, reads each, confirms that what the narrator is saying actually matches what's on screen at that moment. Catches "narrator says 199 changes but the screen shows 44" mistakes.
8. **Hands the video to you.** Path to the `.mp4`, duration, size, and a quick guide on cheap re-runs.

**Wall-clock time: 10–20 minutes for a 3–5 minute demo, depending on how many storyboard iterations you do.**

---

## Iterating without re-doing everything

Demos are made for tweaking. Common changes and their cost:

| You want to change... | What Claude re-runs | Time |
|---|---|---|
| Narration wording or tone | TTS for changed beats only → re-mix → re-brand → re-finalize | ~3 min |
| A click or scroll target | Re-record from that point onward + everything downstream | ~5 min |
| Brand colors or logo | Re-generate the badge → re-brand → re-finalize | ~2 min |
| Captions on/off | Re-finalize only | ~30 sec |
| Background music (file or mood) | Re-finalize only | ~1 min |
| Intro/outro copy | Regenerate slides → re-finalize | ~1 min |

You never have to "start over." Tell Claude what to change in plain English and it knows which steps to re-run.

---

## What it costs

- **OpenAI TTS:** ~$0.10 per 3–5 minute demo. Pay-as-you-go on your own OpenAI account.
- **Everything else:** free. Recording, encoding, captioning, brand overlay, music mixing — all local on your machine.
- **No data leaves your computer** except narration text → OpenAI's TTS endpoint, and the browser visits the site you're demoing.

---

## Limitations to know about

- **The skill drives a real browser.** If your site needs CAPTCHAs, a phone-based 2FA every login, or has aggressive anti-bot protection, recording may need a one-time human login (Claude handles this — opens Chrome, you log in once, the session is saved).
- **Some "demo" pages require live AI processing** (e.g., "generate me a suggestion"). The recorder waits, but if your backend is slow that day the narration may run before the AI output appears. Re-record solves it.
- **The output is 1440×900** by default (good for desktop / YouTube / Loom). Mobile-portrait isn't supported yet.
- **Background music is mixed under narration but doesn't stop** — long demos with intentional silence will keep the music playing. Use `bg_music_volume: 0.2` (or lower) if it feels intrusive.
- **Languages other than English** work for narration (`cedar` and `marin` voices have decent multilingual support) but caption auto-generation hasn't been tuned for non-Latin scripts.

---

## Things that go wrong (and what to do)

| Symptom | Fix |
|---|---|
| Google's sign-in says *"Couldn't sign you in — This browser or app may not be secure"* | Make sure Google Chrome is installed at `/Applications/Google Chrome.app`. Claude uses real Chrome (not Playwright's Chromium) specifically to bypass this block. |
| Captions show as a black rectangle in the final video | Your ffmpeg doesn't include `libass`. Install `ffmpeg-full` (`brew uninstall ffmpeg && brew install ffmpeg-full`) or ask Claude to ship captions as a `.srt` sidecar instead. |
| Narration mentions a number ("five releases") that's not visible at that moment | Claude's final verification step catches this — it'll flag the mismatch and ask you to fix the storyboard. Tell Claude *"fix beat N"* and it rewrites. |
| Background music is too loud / drowns out the narration | Tell Claude *"lower the music"* — it adjusts `bg_music_volume` and re-finalizes (~1 min). Default is 0.4; try 0.25 for very quiet. |
| Recording fails on a click — *"selector not found"* | The site probably changed between your storyboard draft and the recording. Tell Claude to re-explore, regenerate the storyboard, and try again. |

If something else breaks, just paste the error message to Claude. Most issues have known fixes documented in `docs/GOTCHAS.md` and Claude reads it as needed.

---

## For developers (or the curious)

Everything in this folder is open. If you want to understand how it works, or extend it:

- **`SKILL.md`** — the playbook Claude follows to make a demo. Reads top-to-bottom.
- **`docs/SCHEMAS.md`** — the three YAML config files Claude writes per demo (storyboard, branding, demo_config).
- **`docs/GOTCHAS.md`** — every weird issue we ran into building this, with the fix for each. Worth skimming before customizing.
- **`scripts/`** — the eight small Python scripts that do the actual work (one per pipeline stage). Each is < 500 lines and runnable on its own.
- **`examples/`** — complete working demo configs. `halyard-spme/` reproduces a full reference demo from scratch. `oauth-storage-state/` is a template for sites with Google/Microsoft login.

You can hack on individual scripts without breaking anything else — the pipeline is stage-by-stage with named intermediate files. You'll see them in `~/demo-videos/<your-demo-slug>/_intermediate/` after a run.

---

## Quick command reference

If you're driving the pipeline by hand instead of through Claude Code, every stage is one command. From the working directory of a demo:

```bash
uv run scripts/make_overlay.py     --working-dir .
uv run scripts/render_voiceover.py --working-dir .
uv run scripts/record_demo.py      --working-dir .
uv run scripts/mux_demo.py         --working-dir .
uv run scripts/speed_video.py      --input _intermediate/muxed.mp4    --output _intermediate/speed.mp4 --multiplier 1.2
uv run scripts/brand_video.py      --working-dir . --input _intermediate/speed.mp4 --output _intermediate/branded.mp4
uv run scripts/make_intro_outro.py --working-dir .   # if intro/outro features are on
uv run scripts/make_captions.py    --working-dir .   # if captions are on
uv run scripts/finalize_video.py   --working-dir . --input _intermediate/branded.mp4 --output my-demo.mp4
```

But for most users: just talk to Claude Code. It runs these for you in the right order.
