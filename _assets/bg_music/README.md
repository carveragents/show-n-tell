# Bundled bg music library

This directory ships with the `show-n-tell` skill. It backs the `branding.audio.bg_music_mood` config — pick a mood, the skill picks the first track listed for that mood in `library.json`.

## Current state — placeholders

The six mp3s shipped here are **silent 3-minute placeholders**. The pipeline (filter graph, ducking, attribution) works end-to-end with them; the audio just doesn't sound like anything until you swap in real tracks.

## Replacing a placeholder

For each mood you care about, do these four things:

### 1. Pick a real track

Recommended sources, in priority order:

| Source | License | Attribution | Notes |
|---|---|---|---|
| [Pixabay Music](https://pixabay.com/music/) | Pixabay Content License | Not required | Largest catalog, mood tags, free signup gets full API access |
| [Chosic](https://www.chosic.com/free-music/instrumental/) | CC-BY / CC0 | Varies (per track) | Hand-curated, well-tagged |
| [Free Stock Music](https://free-stock-music.com/) | CC0 1.0 Universal | Not required | 320 kbps mp3s, clear licensing |
| [Bensound](https://www.bensound.com/royalty-free-music) | Free License (attribution required) | Required | Loopable instrumentals |

Match the mood criteria:

- `upbeat_morning` — energetic, faster tempo, motivational
- `warm_acoustic_loop` — friendly, mid-tempo, acoustic
- `calm_ambient_piano` — slow, peaceful, ambient
- `playful_uke_strum` — light, bouncy, fun (ukulele, whistle)
- `cinematic_build` — dramatic, building, orchestral
- `tech_modern_pulse` — modern, electronic, minimal

### 2. Normalize to -16 LUFS

```bash
cd ~/.claude/skills/show-n-tell/_assets/bg_music
uvx ffmpeg-normalize <raw-download>.mp3 \
  -o <slug>.mp3 \
  -t -16 \
  --audio-codec libmp3lame \
  -b:a 192k
```

Where `<slug>` is the same filename slot listed in `library.json` (e.g. `warm_acoustic_loop`). Overwrite the placeholder mp3 in place.

Confirm:

```bash
ffmpeg -i <slug>.mp3 -af loudnorm=print_format=summary -f null - 2>&1 | grep "Input Integrated"
```

Expected: roughly `-16.0 LUFS` (±1 dB).

### 3. Update the sidecar JSON

Open `<slug>.json` and replace the PLACEHOLDER fields with real metadata:

```json
{
  "id": "<slug>",
  "title": "Track Name From Source",
  "artist": "Artist or Composer Name",
  "duration_seconds": 184,
  "license": "CC-BY 4.0  /  CC0 1.0  /  Pixabay Content License  /  Bensound Free License",
  "license_url": "https://creativecommons.org/licenses/by/4.0/",
  "source_url": "https://pixabay.com/music/abc-def-1234567/",
  "attribution_text": "Music: \"Track Name\" by Artist (https://source.url)"
}
```

The `attribution_text` field is the exact string `finalize_video.py` prints at Phase 11 hand-off. Make it self-contained — the user reading the console output should know what the track is and where to find more.

### 4. Test

```bash
# In a demo working dir, add to branding.yaml:
#   audio:
#     bg_music_mood: "<mood>"
#     bg_music_volume: 0.4
# Then:
uv run scripts/finalize_video.py \
  --working-dir <demo-dir> \
  --input <demo-dir>/_intermediate/branded.mp4 \
  --output <demo-dir>/test.mp4
```

You should hear the new track ducked under the narration, and the console should print the attribution at the end.

## Adding more moods or tracks per mood

`library.json` is a `mood → [track_ids]` map. The skill picks the **first** ID listed for each mood. Add more entries to expand:

```json
{
  "version": 1,
  "moods": {
    "warm":   ["warm_acoustic_loop", "warm_cafe_jazz"],
    "warm_alt": ["warm_cafe_jazz"]
  }
}
```

Then drop `warm_cafe_jazz.mp3` + `warm_cafe_jazz.json` next to the existing files. The skill reads `library.json` fresh each run; no rebuild needed.

## Why placeholders?

Initial curation requires audio listening capability to judge track fit. The skill author shipped silent placeholders to make the feature testable end-to-end immediately. Real-track curation is left to whoever maintains the skill instance.
