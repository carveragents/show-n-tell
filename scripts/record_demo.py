"""Record the demo webm, beat-by-beat, holding for TTS duration.

CLI:
    uv run scripts/record_demo.py --working-dir <path>

Reads:
    <working_dir>/storyboard.yaml      (beats + actions)
    <working_dir>/branding.yaml        (recording_css)
    <working_dir>/demo_config.yaml     (base_url, viewport, framerate, buffers)
    <working_dir>/_voiceover/manifest.json   (per-beat TTS durations)

Writes:
    <working_dir>/_intermediate/reference.webm
    <working_dir>/_voiceover/timings.json
"""
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml", "playwright"]
# ///
# IMPORTANT: NODE_OPTIONS cleared before importing playwright so the Node driver
# doesn't try to load cmux's restore-node-options.cjs (which won't exist in the
# subprocess context). See docs/GOTCHAS.md #1.
import os
os.environ.pop("NODE_OPTIONS", None)

import argparse
import json
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).parent))
from _lib import (
    load_configs, resolve_working_dir, ensure_dir,
    interp_template, expand_env, load_dotenv_if_present,
)


SKILL_ROOT = Path(__file__).parent.parent
PDF_WRAPPER_HELPER = SKILL_ROOT / "helpers" / "pdf_wrapper.py"


SUPPORTED_ACTIONS = {
    "goto", "goto_and_scroll", "scroll_into_view", "scroll_y",
    "hover", "click", "wait_for_selector", "wait_for_url",
    "goto_pdf", "fill",
}


@dataclass
class ActionContext:
    """Bag of dependencies execute_action needs.

    Keeps the dispatcher signature stable as new action types are added.
    `recording_css` is injected after every navigation; `working_dir` and
    `pdfs_by_id` are only used by `goto_pdf` today but future actions
    (e.g. file uploads, screenshot save) may need them.
    """
    recording_css: str
    working_dir: Path
    pdfs_by_id: dict


def _sanitize_action_for_logging(action: dict) -> dict:
    """Return a copy with `value` masked when the action is a `fill`.

    Used only on the pre_session code path — `fill` is legal in normal
    beats too, but those values aren't credentials, so we don't mask
    there (and avoid creating a false sense of security).
    """
    if action.get("type") == "fill":
        return {**action, "value": "***"}
    return action


SMOOTH_SCROLL_TO_Y_JS = """async ({y, duration}) => {
    const steps = Math.max(10, Math.round(duration / 16));
    const start = window.scrollY;
    const delta = y - start;
    const stepDelay = duration / steps;
    for (let i = 1; i <= steps; i++) {
        const t = i / steps;
        const ease = t < 0.5 ? 2*t*t : -1 + (4 - 2*t)*t;
        window.scrollTo(0, start + delta * ease);
        await new Promise(r => setTimeout(r, stepDelay));
    }
}"""

SMOOTH_SCROLL_TO_EL_JS = """async (selector) => {
    const el = document.querySelector(selector);
    if (!el) return;
    const cs = window.getComputedStyle(el);
    const margin = parseInt(cs.scrollMarginTop || '0', 10);
    const targetY = el.getBoundingClientRect().top + window.scrollY - margin;
    const duration = 900;
    const steps = 60;
    const start = window.scrollY;
    const delta = targetY - start;
    const stepDelay = duration / steps;
    for (let i = 1; i <= steps; i++) {
        const t = i / steps;
        const ease = t < 0.5 ? 2*t*t : -1 + (4 - 2*t)*t;
        window.scrollTo(0, start + delta * ease);
        await new Promise(r => setTimeout(r, stepDelay));
    }
}"""


def smooth_scroll_to_y(page, y, duration_ms=900):
    page.evaluate(SMOOTH_SCROLL_TO_Y_JS, {"y": y, "duration": duration_ms})


def smooth_scroll_to_element(page, selector):
    page.evaluate(SMOOTH_SCROLL_TO_EL_JS, selector)


def page_load_settle(page, recording_css: str):
    if recording_css:
        page.add_style_tag(content=recording_css)
    page.wait_for_timeout(300)


def execute_action(page, action: dict, actx: ActionContext):
    t = action["type"]
    if t not in SUPPORTED_ACTIONS:
        raise ValueError(f"Unknown action type: {t!r}")

    if t == "goto":
        page.goto(action["url"], wait_until="networkidle")
        page_load_settle(page, actx.recording_css)
    elif t == "goto_pdf":
        pdf_id = action["pdf_id"]
        entry = actx.pdfs_by_id.get(pdf_id)
        if not entry:
            raise ValueError(f"goto_pdf: unknown pdf_id={pdf_id!r}; "
                             "declare it under storyboard.yaml `pdfs:`")
        wrapper = (actx.working_dir / "_assets" / "pdf_wrappers"
                   / f"{pdf_id}_p{entry['page']}.html")
        if not wrapper.exists():
            raise FileNotFoundError(f"PDF wrapper missing: {wrapper}")
        page.goto(f"file://{wrapper.resolve()}", wait_until="networkidle")
        page_load_settle(page, actx.recording_css)
    elif t == "goto_and_scroll":
        page.goto(action["url"], wait_until="networkidle")
        page_load_settle(page, actx.recording_css)
        smooth_scroll_to_element(page, action["selector"])
    elif t == "scroll_y":
        smooth_scroll_to_y(page, action["y"], action.get("duration_ms", 900))
    elif t == "scroll_into_view":
        smooth_scroll_to_element(page, action["selector"])
    elif t == "hover":
        # Auto-scroll-into-view if not currently visible (GOTCHAS #14)
        loc = page.locator(action["selector"]).first
        try:
            if not loc.is_visible(timeout=500):
                smooth_scroll_to_element(page, action["selector"])
        except Exception:
            smooth_scroll_to_element(page, action["selector"])
        loc.hover()
    elif t == "click":
        loc = page.locator(action["selector"]).first
        try:
            if not loc.is_visible(timeout=500):
                smooth_scroll_to_element(page, action["selector"])
        except Exception:
            smooth_scroll_to_element(page, action["selector"])
        loc.click()
        page.wait_for_timeout(200)
        if action.get("then_scroll"):
            smooth_scroll_to_element(page, action["then_scroll"])
    elif t == "fill":
        page.locator(action["selector"]).first.fill(action["value"])
    elif t == "wait_for_selector":
        page.wait_for_selector(action["selector"], timeout=action.get("timeout_ms", 5000))
    elif t == "wait_for_url":
        page.wait_for_url(lambda url: action["contains"] in url, timeout=10000)


def run_pre_session(page, steps, actx: ActionContext):
    """Execute pre-recording setup steps (e.g. login). Values must already
    be `expand_env`-resolved before being passed here.

    Credentials (`fill.value`) are masked in all stdout so secrets pulled
    from `${ENV_VAR}` don't leak into logs.
    """
    for step in steps:
        safe = _sanitize_action_for_logging(step)
        t0 = time.monotonic()
        try:
            execute_action(page, step, actx)
        except Exception as e:
            raise RuntimeError(
                f"pre_session step failed: {safe!r}: {e}"
            ) from e
        dt_ms = int((time.monotonic() - t0) * 1000)
        selector = safe.get("selector") or safe.get("url") or safe.get("contains") or ""
        print(f"  pre-session  {safe['type']:14}  {dt_ms:5}ms  {selector}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--working-dir", required=True)
    args = ap.parse_args()

    wd = resolve_working_dir(args.working_dir)
    load_dotenv_if_present(wd)

    storyboard, branding, demo_config = load_configs(wd)
    base_url = demo_config.get("site", {}).get("base_url", "").rstrip("/")
    if not base_url:
        sys.exit("demo_config.yaml: site.base_url is required")

    rec_cfg = demo_config.get("recording", {})
    viewport = rec_cfg.get("viewport", {"width": 1440, "height": 900})
    pre_ms = int(rec_cfg.get("pre_narration_ms", 400))
    post_ms = int(rec_cfg.get("post_narration_ms", 700))

    recording_css = branding.get("recording_css", "") or ""

    manifest_path = wd / "_voiceover" / "manifest.json"
    if not manifest_path.exists():
        sys.exit(f"Missing {manifest_path}. Run render_voiceover.py first.")
    manifest = json.loads(manifest_path.read_text())
    durations = {b["id"]: b["duration_seconds"] for b in manifest["beats"]}

    beats = storyboard.get("beats", [])
    missing = [b["id"] for b in beats if b["id"] not in durations]
    if missing:
        sys.exit(f"Missing voiceover for beats: {missing}. "
                 "Re-run render_voiceover.py.")

    # Template-expand `{{ base_url }}` in every action URL
    ctx = {"base_url": base_url}
    expanded_beats = [
        {**b, "action": interp_template(b["action"], ctx)} for b in beats
    ]

    pre_session = demo_config.get("session", {}).get("pre_session") or []
    # pre_session steps get BOTH {{ base_url }} interpolation AND ${ENV_VAR}
    # expansion so credentials in `.env` resolve (see SCHEMAS.md "Login flow").
    expanded_pre = [expand_env(interp_template(s, ctx)) for s in pre_session]

    # PDF pre-flight: render an HTML wrapper for every entry in `pdfs:`.
    # Skipped silently if the wrapper already exists (idempotent).
    pdfs = storyboard.get("pdfs", []) or []
    pdfs_by_id = {p["id"]: p for p in pdfs}
    if pdfs:
        print(f"PDF pre-flight: {len(pdfs)} pdf(s)…")
        for entry in pdfs:
            pdf_id = entry["id"]
            page_num = entry["page"]
            wrapper = (wd / "_assets" / "pdf_wrappers"
                       / f"{pdf_id}_p{page_num}.html")
            if wrapper.exists():
                print(f"  reuse  {pdf_id} p{page_num}")
                continue
            source = expand_env(interp_template(entry["source"], ctx))
            cmd = [
                "uv", "run", str(PDF_WRAPPER_HELPER),
                "--working-dir", str(wd),
                "--pdf-id", pdf_id,
                "--pdf-source", source,
                "--page", str(page_num),
            ]
            if entry.get("citation"):
                cmd += ["--citation", interp_template(entry["citation"], ctx)]
            subprocess.run(cmd, check=True)
        print()

    out_dir = ensure_dir(wd / "_intermediate")
    video_tmp = ensure_dir(wd / "_intermediate" / "_video_tmp")
    video_out = out_dir / "reference.webm"
    timings_out = wd / "_voiceover" / "timings.json"

    timings = []
    print(f"Recording {len(expanded_beats)} beats…\n")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx_kwargs = dict(
            viewport=viewport,
            record_video_dir=str(video_tmp),
            record_video_size=viewport,
        )
        playwright_ctx = browser.new_context(**ctx_kwargs)
        if recording_css:
            playwright_ctx.add_init_script(f"""
                (() => {{
                    const style = document.createElement('style');
                    style.textContent = `{recording_css}`;
                    document.head.appendChild(style);
                }})();
            """)

        page = playwright_ctx.new_page()

        actx = ActionContext(
            recording_css=recording_css,
            working_dir=wd,
            pdfs_by_id=pdfs_by_id,
        )

        if expanded_pre:
            print(f"Running pre-session ({len(expanded_pre)} steps)…")
            try:
                run_pre_session(page, expanded_pre, actx)
            except Exception as e:
                sys.exit(f"\n✗ {e}")
            print("  ✓ pre-session complete\n")

        beat_start = time.monotonic()
        for beat in expanded_beats:
            t0 = time.monotonic()
            try:
                execute_action(page, beat["action"], actx)
            except Exception as e:
                sys.exit(f"\n✗ beat {beat['id']!r} failed during action "
                         f"{beat['action']!r}: {e}")
            action_ms = int((time.monotonic() - t0) * 1000)

            tts_ms = int(durations[beat["id"]] * 1000)
            page.wait_for_timeout(pre_ms + tts_ms + post_ms)

            total_ms = int((time.monotonic() - t0) * 1000)
            timings.append({
                "id": beat["id"],
                "action_ms": action_ms,
                "tts_ms": tts_ms,
                "pre_ms": pre_ms,
                "post_ms": post_ms,
                "total_ms": total_ms,
            })
            print(f"  {beat['id']:32}  action {action_ms:5}ms · tts {tts_ms:5}ms · "
                  f"total {total_ms:5}ms")

        total_video_ms = int((time.monotonic() - beat_start) * 1000)
        print(f"\nVideo body wall-time: {total_video_ms/1000:.1f}s")

        video_path = page.video.path()
        playwright_ctx.close()
        browser.close()

    if video_path and Path(video_path).exists():
        shutil.move(video_path, video_out)
    if video_tmp.exists():
        shutil.rmtree(video_tmp)

    timings_out.write_text(json.dumps({
        "viewport": viewport,
        "pre_narration_ms": pre_ms,
        "post_narration_ms": post_ms,
        "beats": timings,
    }, indent=2))

    print(f"\n✓ Video: {video_out} ({video_out.stat().st_size / 1_048_576:.1f} MB)")
    print(f"✓ Timings: {timings_out}")


if __name__ == "__main__":
    main()
