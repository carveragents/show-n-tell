# Background music for demos

**Status:** Drafted 2026-05-13, awaiting user review
**Author:** Claude (Opus 4.7) with achint
**Phase:** B+ (companion to Phase B's intro/outro + captions)

## Problem

Demos produced by the skill have narration over silence. There's no music bed under the voiceover, which makes them feel flat compared to typical product walkthroughs. Users want music. Some users have a track they want to use; others want the skill to pick one for them based on the demo's mood.

## Goal

Two paths to a music bed, mixed under the narration with natural-sounding sidechain ducking:

- **Mode A — user-provided file.** They drop an mp3/wav/flac/ogg path into `branding.yaml`.
- **Mode B — auto-pick from bundled library.** They specify a mood ("warm", "upbeat", etc.) and the skill picks a track from a small library shipped with the skill itself.

The music plays from the start of the intro slide through the end of the outro slide, ducks under the narration during voiceover segments, and rises during silences. Single encode pass — no extra quality loss.

## Non-goals

- **Network calls for track discovery.** Decided against Jamendo/Pixabay/etc. — bundled library is offline and deterministic. If users want more variety, they can drop a custom file via Mode A.
- **Per-beat music changes.** One track plays under the whole demo.
- **Custom volume curves / fade points.** Linear fade in (1s) at start, linear fade out (2s) at end, sidechain ducking handles the rest.
- **Loop-point crossfading.** Simple `aloop` for tracks shorter than the demo. If users complain about audible loop clicks, revisit.
- **License sidecar files alongside the mp4.** Attribution prints to the console at hand-off only.

## Design

### Config additions to `branding.yaml`

```yaml
audio:
  # Exactly one of these two; both empty = no bg music (back-compat default).
  bg_music_path: "./_assets/my_music.mp3"   # Mode A — local file
  bg_music_mood: "warm"                     # Mode B — bundled library lookup
  bg_music_volume: 0.4                      # Baseline volume before ducking
                                            # (default 0.4 with ducking on)
```

Validation: if both `bg_music_path` AND `bg_music_mood` are set → error at Phase 5 ("specify one, not both"). If neither is set → no bg music, pipeline behaves exactly as today.

### Bundled library structure

Library lives **inside the skill folder**, not the working dir:

```
~/.claude/skills/show-n-tell/_assets/bg_music/
├── library.json                   # mood → [track_ids] index
├── upbeat_morning.mp3             # ~3-5 min loopable track
├── upbeat_morning.json            # metadata + attribution
├── warm_acoustic_loop.mp3
├── warm_acoustic_loop.json
├── calm_ambient_piano.mp3
├── calm_ambient_piano.json
├── playful_uke_strum.mp3
├── playful_uke_strum.json
├── cinematic_build.mp3
├── cinematic_build.json
└── tech_modern_pulse.mp3
└── tech_modern_pulse.json
```

`library.json`:

```json
{
  "version": 1,
  "moods": {
    "upbeat":    ["upbeat_morning"],
    "warm":      ["warm_acoustic_loop"],
    "calm":      ["calm_ambient_piano"],
    "playful":   ["playful_uke_strum"],
    "cinematic": ["cinematic_build"],
    "tech":      ["tech_modern_pulse"]
  }
}
```

Per-track metadata file:

```json
{
  "id": "warm_acoustic_loop",
  "title": "Acoustic Breeze",
  "artist": "Bensound (Benjamin Tissot)",
  "duration_seconds": 184,
  "license": "Bensound Free License",
  "license_url": "https://www.bensound.com/licensing",
  "source_url": "https://www.bensound.com/royalty-free-music/track/acoustic-breeze",
  "attribution_text": "Music: \"Acoustic Breeze\" by Bensound (https://www.bensound.com)"
}
```

### Mood vocabulary

Six moods in v1 — constrained, since the auto-pick maps directly to a curated track:

| Mood | Feel | Use case |
|---|---|---|
| `upbeat` | Energetic, faster tempo | Product launches, motivation pitches |
| `warm` | Friendly, mid-tempo, acoustic | Most product demos (sensible default for casual tone) |
| `calm` | Slow, peaceful, ambient | Reflective / explainer-style demos |
| `playful` | Light, bouncy, fun | Consumer apps with playful brands |
| `cinematic` | Dramatic, building | High-stakes pitches, fundraising decks |
| `tech` | Modern, electronic, professional | B2B SaaS, dev tools |

If the user specifies an unknown mood → error listing the supported set.

### Track sourcing (one-time curation during implementation)

For each of the six moods, pick one royalty-free track from these sources, in priority order:

1. **Bensound** (CC-BY-3.0 with attribution required, or free Bensound License with attribution) — has well-mixed loopable instrumentals across the mood vocabulary.
2. **Mixkit Free Music** (Mixkit License, no attribution required) — fallback if Bensound doesn't have a good fit.
3. **Pixabay Music** (Pixabay Content License, no attribution required) — another fallback.

The curation step happens once. Tracks get downloaded, normalized to -16 LUFS (so volume is consistent regardless of source), and committed to the skill folder.

### Selection logic

Mode B (mood-based):

1. Load `<skill>/_assets/bg_music/library.json`
2. Look up `library.moods[bg_music_mood]` → list of track IDs
3. Pick the **first** ID in the list (deterministic; users can re-order library.json to change defaults)
4. Resolve `<skill>/_assets/bg_music/<id>.mp3`
5. Pass that path forward as if it were a Mode A user-provided file

This is intentionally simple. No random choice, no duration-aware selection — just "first match wins".

### Sidechain ducking

Narration is the sidechain trigger. When narration plays loud, bg music compresses (ducks) down by ~14dB. When narration is silent, bg music springs back to baseline.

In `finalize_video.py`'s ffmpeg filter graph:

```
[3:a] aloop=loop=-1:size=2e9, volume=0.4 [bg_loud]                             # loop + baseline volume
[bg_loud] afade=t=in:st=0:d=1, afade=t=out:st=END-2:d=2 [bg_faded]              # 1s fade in, 2s fade out
[narration_chain] asplit=2 [narr_out] [narr_side]                               # split narration for sidechain trigger
[bg_faded] [narr_side] sidechaincompress=threshold=0.05:ratio=8:attack=20:release=400 [bg_ducked]
[narr_out] [bg_ducked] amix=inputs=2:duration=first [final_audio]
```

Parameters tuned for marin/cedar TTS voices:
- `threshold=0.05` — narration loudness above 0.05 triggers ducking
- `ratio=8` — 8:1 compression (strong duck of ~14dB)
- `attack=20` ms — fast clamp when speech starts
- `release=400` ms — smooth rise back over 400ms after speech ends

May need a tuning pass after first listen. Document the params in `docs/SCHEMAS.md` so users can override per-demo if a particular voice clashes.

### Pipeline integration

**Phase 5 (working dir setup):** new validation step `_lib.resolve_bg_music_path(branding)` returns the absolute mp3 path or `None`. Errors fail fast with actionable messages.

**Phase 9 (post-processing):** modify `scripts/finalize_video.py` to:
- Accept the resolved bg music path (None = skip)
- Add the bg music as a fourth ffmpeg input
- Insert the ducking filter chain after the existing audio crossfade chain
- Map `[final_audio]` instead of the current narration-only `[a]` output

No new pipeline script. Everything stays in `finalize_video.py` so we keep the single encode pass.

**Phase 11 (hand off):** print attribution if music was used:

```
Music: "Acoustic Breeze" by Bensound (https://www.bensound.com)
       Licensed under Bensound Free License
```

Pulled from the track's sidecar `<id>.json`.

### Branch on `features.crossfade_seconds`

`finalize_video.py` already branches on `crossfade_seconds`: zero = concat demuxer with `-c copy`, non-zero = xfade filter graph + re-encode.

With bg music: the `-c copy` path **breaks** because we need to mix new audio in. So when bg music is enabled, we always go through the filter-graph re-encode path even if `crossfade_seconds == 0`. The xfade filter still runs but with `duration=0` and `offset=intro_duration` — effectively a hard cut on video, with the bg music smoothly bridging the seam.

This trades the no-re-encode optimization for music support. Acceptable — users who care about lossless concat probably won't enable music anyway.

### Failure modes

| Condition | Behavior |
|---|---|
| Both `bg_music_path` and `bg_music_mood` set | Phase 5 fail-fast: "Set one, not both" |
| `bg_music_path` set, file missing | Phase 5 fail-fast: actionable error with resolved path |
| `bg_music_mood` not in library | Phase 5 fail-fast: list valid moods |
| Track mp3 file missing despite library.json entry | Phase 5 fail-fast: skill installation corrupted, suggest re-clone |
| Track shorter than video | aloop handles it; minor click at boundary may be audible |
| ffmpeg `sidechaincompress` filter unavailable | Edge case — fail at Phase 9 with actionable error pointing at ffmpeg-full |

### Updates to docs + examples

- **`docs/SCHEMAS.md`**: new `audio:` block under branding, mood vocabulary table, ducking param reference
- **`docs/GOTCHAS.md`**: new entry on track volume normalization (-16 LUFS) and what happens if user supplies a non-normalized file
- **`docs/CLAUDE.md`**: new preserve invariant — "Bundled bg_music library is part of the skill; do not relocate or rename without updating `library.json`."
- **`examples/oauth-storage-state/branding.yaml`**: add commented-out `audio:` block as reference
- **`SKILL.md` Phase 6 + Phase 11**: mention bg music when relevant
- New CLAUDE.md non-negotiable: "Print music attribution at Phase 11 hand-off if music was auto-picked from the bundled library."

## Testing

### Unit — `tests/test_bg_music.py`

1. `_lib.resolve_bg_music_path` with both fields set → raises
2. With Mode A path → returns absolute path
3. With Mode A path missing → raises with resolved path in message
4. With Mode B mood unknown → raises listing valid moods
5. With Mode B mood valid → returns path to library track
6. With neither field → returns None

### Integration — `tests/test_finalize_bg_music_e2e.py`

End-to-end with a tiny test demo:

1. Set up a working dir with a 30s reference video + matching narration
2. Add `bg_music_mood: warm` to branding
3. Run `finalize_video.py`
4. Probe final mp4 audio stream — confirm:
   - Audio is 2-channel mixed (narration + music)
   - Mean RMS during narration timestamp > mean RMS during silence (because music ducks)
   - Duration matches expected

Also: run with `bg_music_mood: nonexistent` and confirm fail-fast.

### Manual listening pass

Skill author / user listens to the final mp4 with each mood and confirms:
- Music is audible but doesn't overpower narration
- Ducking transitions feel natural (no abrupt jumps)
- Fade in/out at start/end of demo is smooth
- Loop point is not jarring (if demo > track duration)

## Implementation order

Per subagent-driven-development per the user's stated workflow preference:

1. **Schema + docs first** — update `docs/SCHEMAS.md` + `docs/GOTCHAS.md` placeholder entry. Haiku tier. One commit.
2. **`_lib.resolve_bg_music_path` + unit tests** — Haiku (mechanical, fully specced). One commit.
3. **Bundle the library** — curate + download 6 tracks, normalize to -16 LUFS, write `library.json` + per-track metadata. Manual step done by user/me with `ffmpeg-normalize`. One commit.
4. **Modify `finalize_video.py`** — add the bg music input + filter chain + branch override for crossfade=0 path. Sonnet (filter graph is non-trivial, codec audit needed). One commit.
5. **Integration test** — `tests/test_finalize_bg_music_e2e.py` with audio RMS verification. Sonnet (multi-step). One commit.
6. **Hand-off print + SKILL.md updates** — Haiku. One commit.

Each task gets implementer + spec reviewer (Sonnet) + code quality reviewer (Sonnet) per the subagent-driven-development pattern.

## Open questions

None. All four review questions from the brainstorming round were resolved:
- Provider: bundled library (you chose)
- Ducking: sidechain (you chose, "should sound natural")
- Mood vocabulary: constrained 6-mood set (my call given bundled library)
- Attribution: console only (you chose)
