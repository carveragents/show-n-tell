"""Unit tests for _lib.resolve_bg_music_path()."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from _lib import resolve_bg_music_path  # noqa: E402


def _make_library(skill_dir: Path, moods_to_tracks: dict,
                  create_track_files: bool = True) -> None:
    bgm = skill_dir / "_assets" / "bg_music"
    bgm.mkdir(parents=True)
    (bgm / "library.json").write_text(
        json.dumps({"version": 1, "moods": moods_to_tracks})
    )
    if create_track_files:
        for tracks in moods_to_tracks.values():
            for tid in tracks:
                (bgm / f"{tid}.mp3").touch()


def test_neither_set_returns_none(tmp_path):
    assert resolve_bg_music_path({}, working_dir=tmp_path, skill_dir=tmp_path) is None
    assert resolve_bg_music_path({"audio": {}},
                                 working_dir=tmp_path, skill_dir=tmp_path) is None


def test_both_set_raises(tmp_path):
    branding = {"audio": {"bg_music_path": "./x.mp3", "bg_music_mood": "warm"}}
    with pytest.raises(ValueError, match="exactly one"):
        resolve_bg_music_path(branding, working_dir=tmp_path, skill_dir=tmp_path)


def test_path_mode_relative_to_working_dir(tmp_path):
    (tmp_path / "my.mp3").touch()
    branding = {"audio": {"bg_music_path": "./my.mp3"}}
    result = resolve_bg_music_path(branding, working_dir=tmp_path, skill_dir=tmp_path)
    assert result == (tmp_path / "my.mp3").resolve()


def test_path_mode_absolute(tmp_path):
    target = tmp_path / "elsewhere" / "track.mp3"
    target.parent.mkdir()
    target.touch()
    branding = {"audio": {"bg_music_path": str(target)}}
    result = resolve_bg_music_path(branding, working_dir=tmp_path, skill_dir=tmp_path)
    assert result == target.resolve()


def test_path_mode_missing_file_raises(tmp_path):
    branding = {"audio": {"bg_music_path": "./missing.mp3"}}
    with pytest.raises(FileNotFoundError, match="missing.mp3"):
        resolve_bg_music_path(branding, working_dir=tmp_path, skill_dir=tmp_path)


def test_mood_mode_resolves_first_track(tmp_path):
    _make_library(tmp_path, {"warm": ["warm_a", "warm_b"]})
    branding = {"audio": {"bg_music_mood": "warm"}}
    result = resolve_bg_music_path(branding, working_dir=tmp_path, skill_dir=tmp_path)
    assert result == (tmp_path / "_assets" / "bg_music" / "warm_a.mp3").resolve()


def test_unknown_mood_lists_valid_options(tmp_path):
    _make_library(tmp_path, {"warm": ["w"], "upbeat": ["u"]})
    branding = {"audio": {"bg_music_mood": "spicy"}}
    with pytest.raises(ValueError) as exc:
        resolve_bg_music_path(branding, working_dir=tmp_path, skill_dir=tmp_path)
    msg = str(exc.value)
    assert "spicy" in msg
    assert "upbeat" in msg and "warm" in msg


def test_mood_track_mp3_missing(tmp_path):
    _make_library(tmp_path, {"warm": ["warm_missing"]}, create_track_files=False)
    branding = {"audio": {"bg_music_mood": "warm"}}
    with pytest.raises(FileNotFoundError, match="warm_missing.mp3"):
        resolve_bg_music_path(branding, working_dir=tmp_path, skill_dir=tmp_path)


def test_mood_with_empty_tracklist_raises(tmp_path):
    _make_library(tmp_path, {"warm": []})
    branding = {"audio": {"bg_music_mood": "warm"}}
    with pytest.raises(ValueError, match="no tracks"):
        resolve_bg_music_path(branding, working_dir=tmp_path, skill_dir=tmp_path)


def test_library_json_missing(tmp_path):
    branding = {"audio": {"bg_music_mood": "warm"}}
    with pytest.raises(FileNotFoundError, match="library.json"):
        resolve_bg_music_path(branding, working_dir=tmp_path, skill_dir=tmp_path)


def test_path_mode_tilde_expands_to_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "track.mp3").touch()
    branding = {"audio": {"bg_music_path": "~/track.mp3"}}
    result = resolve_bg_music_path(branding,
                                   working_dir=tmp_path / "wd",
                                   skill_dir=tmp_path)
    assert result == (tmp_path / "track.mp3").resolve()


def test_empty_path_string_raises(tmp_path):
    branding = {"audio": {"bg_music_path": ""}}
    with pytest.raises(ValueError, match="empty string"):
        resolve_bg_music_path(branding, working_dir=tmp_path, skill_dir=tmp_path)


def test_empty_mood_string_raises(tmp_path):
    branding = {"audio": {"bg_music_mood": ""}}
    with pytest.raises(ValueError, match="empty string"):
        resolve_bg_music_path(branding, working_dir=tmp_path, skill_dir=tmp_path)


def test_corrupted_library_json_raises_value_error(tmp_path):
    (tmp_path / "_assets" / "bg_music").mkdir(parents=True)
    (tmp_path / "_assets" / "bg_music" / "library.json").write_text("{not valid json")
    branding = {"audio": {"bg_music_mood": "warm"}}
    with pytest.raises(ValueError, match="not valid JSON"):
        resolve_bg_music_path(branding, working_dir=tmp_path, skill_dir=tmp_path)
