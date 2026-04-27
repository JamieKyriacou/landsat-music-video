#!/usr/bin/env python3
"""
Landsat Song Line Video Generator

Downloads a song, finds word-level timings with Whisper, generates Landsat
letter-art images for each word, and renders a synced 1080×1920 MP4.

Pass --line multiple times for consecutive lines — they are matched in order
so repeated lines (e.g. a chorus) resolve to the right occurrence.

Usage:
  # single line
  python3 landsat_video.py --song "Pink Floyd Wish You Were Here" \
                           --line "How I wish how I wish you were here"

  # multiple lines
  python3 landsat_video.py --song "Pink Floyd Wish You Were Here" \
                           --line "How I wish how I wish you were here" \
                           --line "We're just two lost souls swimming in a fish bowl"

  # local audio file
  python3 landsat_video.py --audio /path/to/song.mp3 \
                           --line "first line" \
                           --line "second line"
"""

import sys
import re
import subprocess
import argparse
import tempfile
from pathlib import Path

# Always resolve tools that live inside the same venv as this script
_PYTHON = sys.executable

import whisper
import requests

from landsat_words import build_word_image, make_card, safe_name


# ── helpers ────────────────────────────────────────────────────────────────────

def strip_punct(word: str) -> str:
    """Remove all non-alpha characters and lowercase."""
    return re.sub(r"[^a-z]", "", word.lower())


def section(title: str) -> None:
    print(f"\n── {title} {'─' * max(0, 46 - len(title))}")


# ── audio download ─────────────────────────────────────────────────────────────

def download_audio(query: str, out_dir: Path) -> Path:
    dest_template = str(out_dir / "audio.%(ext)s")
    print(f"  Query : {query!r}")
    subprocess.run(
        [
            _PYTHON, "-m", "yt_dlp",
            f"ytsearch1:{query}",
            "--extract-audio",
            "--audio-format", "mp3",
            "--audio-quality", "0",
            "-o", dest_template,
            "--no-playlist",
            "--quiet", "--progress",
        ],
        check=True,
    )
    result = out_dir / "audio.mp3"
    if not result.exists():
        raise FileNotFoundError(f"yt-dlp did not create {result}")
    return result


# ── whisper transcription ──────────────────────────────────────────────────────

def transcribe(audio_path: Path, model_size: str) -> list[dict]:
    """Return a flat list of {word, start, end} dicts for every spoken word."""
    print(f"  Model : {model_size}")
    model = whisper.load_model(model_size)
    print(f"  File  : {audio_path.name}")
    result = model.transcribe(
        str(audio_path),
        word_timestamps=True,
        language="en",
        verbose=False,
    )
    flat = []
    for seg in result["segments"]:
        for w in seg.get("words", []):
            cw = strip_punct(w["word"])
            if cw:
                flat.append({"word": cw, "start": w["start"], "end": w["end"]})
    print(f"  Found : {len(flat)} words in transcript")
    return flat


# ── line matching ──────────────────────────────────────────────────────────────

def match_line(
    all_words: list[dict],
    target_words: list[str],
    start_from: int = 0,
) -> tuple[list[dict], int]:
    """
    Sliding-window search for target_words inside all_words[start_from:].
    Searching after the previous match means repeated lines (choruses) resolve
    to the correct occurrence rather than always matching the first one.

    Returns (matched timing dicts, index of first word after the match).
    """
    target = [strip_punct(w) for w in target_words]
    n = len(target)

    best_score, best_i = -1, start_from
    for i in range(start_from, max(start_from + 1, len(all_words) - n + 1)):
        window = [w["word"] for w in all_words[i: i + n]]
        score = sum(a == b for a, b in zip(target, window))
        if score > best_score:
            best_score, best_i = score, i
            if score == n:
                break   # perfect match — stop early

    pct = int(100 * best_score / n)
    print(f"    Match : {best_score}/{n} words ({pct}%)")
    if pct < 50:
        print("    WARN  : low match — Whisper may have struggled with this passage")

    return all_words[best_i: best_i + n], best_i + n


# ── ffmpeg helpers ─────────────────────────────────────────────────────────────

def write_concat(images: list[Path], timings: list[dict], path: Path) -> None:
    """
    Build an ffmpeg concat-demuxer file.
    Each image is held until the next word begins; the last image is held for
    its own spoken duration (minimum 0.5 s).
    """
    lines = []
    for i, (img, t) in enumerate(zip(images, timings)):
        if i + 1 < len(timings):
            dur = timings[i + 1]["start"] - t["start"]
        else:
            dur = max(t["end"] - t["start"], 0.5)
        lines += [f"file '{img.resolve()}'", f"duration {dur:.4f}"]

    # ffmpeg concat demuxer requires the last entry listed twice
    lines.append(f"file '{images[-1].resolve()}'")
    path.write_text("\n".join(lines) + "\n")


def render(concat: Path, audio: Path, t_start: float, t_end: float, out: Path) -> None:
    """Trim audio to the line, then combine with the image sequence."""
    trimmed = concat.parent / "line.aac"

    # 1. Trim audio
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", str(audio),
            "-ss", f"{t_start:.4f}",
            "-to", f"{t_end:.4f}",
            "-c:a", "aac", "-b:a", "192k",
            str(trimmed),
        ],
        check=True,
        capture_output=True,
    )

    # 2. Encode video
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0", "-i", str(concat),
            "-i", str(trimmed),
            "-c:v", "libx264", "-preset", "medium",
            "-pix_fmt", "yuv420p",
            "-c:a", "copy",
            "-shortest",
            str(out),
        ],
        check=True,
    )


# ── main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Synced Landsat song-line video")
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--song",  help="Song search query — downloaded via yt-dlp")
    src.add_argument("--audio", type=Path, help="Local audio file (mp3 / wav / flac …)")
    parser.add_argument(
        "--line", dest="lines", action="append", metavar="LINE",
        help="A line to animate. Repeat for multiple lines (matched in order). "
             "Omit entirely to animate the whole song.",
    )
    parser.add_argument(
        "--model", default="small",
        choices=["tiny", "base", "small", "medium", "large"],
        help="Whisper model size (default: small; larger = slower but more accurate)",
    )
    args = parser.parse_args()

    full_song_mode = not args.lines

    # Parse explicit lines (stripped of punctuation)
    lines_words: list[list[str]] = []
    if not full_song_mode:
        for raw in args.lines:
            words = re.sub(r"[^\w\s]", "", raw).split()
            if words:
                lines_words.append(words)
        if not lines_words:
            print("No words found in any line."); sys.exit(1)

    tmp = Path(tempfile.mkdtemp(prefix="landsat_"))

    # ── 1. Audio ───────────────────────────────────────────────────────────────
    section("Audio")
    if args.audio:
        audio_path = args.audio
        print(f"  File  : {audio_path}")
    else:
        audio_path = download_audio(args.song, tmp)
        print(f"  Saved : {audio_path}")

    # ── 2. Transcribe ──────────────────────────────────────────────────────────
    section("Transcribing with Whisper")
    all_words = transcribe(audio_path, args.model)

    # ── 3. Resolve words + timings ─────────────────────────────────────────────
    if full_song_mode:
        # Use every word Whisper found — no matching needed
        section("Mode: full song")
        flat_timings = all_words          # already {word, start, end}
        flat_words   = [w["word"] for w in all_words]
        print(f"  {len(flat_words)} words across full song")

        # Folder named after the song/audio source
        if args.song:
            slug = safe_name(args.song)
        else:
            slug = safe_name(audio_path.stem)
    else:
        # Match each explicit line in transcript order
        section("Matching lines")
        total_words = sum(len(w) for w in lines_words)
        print(f"  {len(lines_words)} line(s), {total_words} words\n")

        flat_timings: list[dict] = []
        flat_words:   list[str]  = []
        cursor = 0
        for i, words in enumerate(lines_words, 1):
            print(f"  Line {i}: {' '.join(words)}")
            timings, cursor = match_line(all_words, words, start_from=cursor)
            for word, t in zip(words, timings):
                print(f"    {word:<20}  {t['start']:>6.2f}s – {t['end']:.2f}s")
                flat_words.append(word)
                flat_timings.append(t)

        # Folder named after the first line
        slug = safe_name(" ".join(lines_words[0]))

    # ── 4. Generate images ─────────────────────────────────────────────────────
    section("Generating Landsat images")
    out_base = Path("output") / slug
    raw_dir  = out_base / "raw"
    fmt_dir  = out_base / "formatted"
    raw_dir.mkdir(parents=True, exist_ok=True)
    fmt_dir.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (compatible; LandsatWordArt/1.0)",
        "Referer":    "https://science.nasa.gov/specials/your-name-in-landsat/",
    })

    # Gaps between lines (or any silent stretch) are handled automatically:
    # each image's duration in the concat file runs until the next word begins.
    fmt_images: list[Path] = []
    used_timings: list[dict] = []
    n_total = len(flat_words)

    for idx, (word, timing) in enumerate(zip(flat_words, flat_timings), 1):
        if not any(c.isalpha() for c in word):
            continue
        print(f"  [{idx:0{len(str(n_total))}d}/{n_total}] '{word}'")
        raw_img = build_word_image(word, session)
        stem    = f"{idx:0{len(str(n_total))}d}_{safe_name(word)}.jpg"
        raw_img.save(raw_dir / stem, "JPEG", quality=92)
        card = make_card(raw_img)
        card_path = fmt_dir / stem
        card.save(card_path, "JPEG", quality=92)
        fmt_images.append(card_path)
        used_timings.append(timing)

    # ── 5. Render video ────────────────────────────────────────────────────────
    section("Rendering video")
    concat_path = out_base / "concat.txt"
    write_concat(fmt_images, used_timings, concat_path)

    video_path = out_base / "video.mp4"
    t_start = used_timings[0]["start"]
    t_end   = used_timings[-1]["end"] + 0.3

    print(f"  Audio : {t_start:.2f}s → {t_end:.2f}s  ({t_end - t_start:.2f}s total)")
    print(f"  Output: {video_path}")
    render(concat_path, audio_path, t_start, t_end, video_path)

    print(f"\nDone → {video_path.resolve()}")


if __name__ == "__main__":
    main()
