#!/usr/bin/env python3
"""
Landsat Word Art Generator
Takes a sentence and creates Landsat satellite imagery for each word.

Two output folders are written inside output/<sentence>/:
  raw/       — stitched word images at native resolution
  formatted/ — each image centred on a 1080×1920 white canvas with 50 px border

Usage:
  python3 landsat_words.py "hello world"
  python3 landsat_words.py          # prompts for input
"""

import sys
import random
import argparse
from pathlib import Path
from io import BytesIO

import requests
from PIL import Image

BASE_URL = "https://science.nasa.gov/specials/your-name-in-landsat/images"

# How many image variants exist per letter (variants are 0-indexed)
LETTER_VARIANTS = {
    'a': 5, 'b': 2, 'c': 3, 'd': 2, 'e': 4,
    'f': 2, 'g': 1, 'h': 2, 'i': 5, 'j': 3,
    'k': 2, 'l': 4, 'm': 3, 'n': 3, 'o': 2,
    'p': 2, 'q': 2, 'r': 4, 's': 3, 't': 2,
    'u': 2, 'v': 4, 'w': 2, 'x': 3, 'y': 2,
    'z': 2,
}


def fetch_letter_image(letter: str, session: requests.Session) -> Image.Image:
    """Download a random Landsat satellite variant image for the given letter."""
    letter = letter.lower()
    if letter not in LETTER_VARIANTS:
        raise ValueError(f"No Landsat image for character '{letter}'")

    variant = random.randint(0, LETTER_VARIANTS[letter] - 1)
    url = f"{BASE_URL}/{letter}_{variant}.jpg"

    response = session.get(url, timeout=15)
    response.raise_for_status()
    return Image.open(BytesIO(response.content)).convert("RGB")


def build_word_image(word: str, session: requests.Session) -> Image.Image:
    """
    Fetch a Landsat image for each letter in the word and stitch them
    together horizontally into a single composite image.
    """
    letters = [c for c in word if c.isalpha()]
    if not letters:
        raise ValueError(f"'{word}' contains no alphabetic characters")

    print(f"    fetching {len(letters)} letter(s): ", end="", flush=True)
    tiles = []
    for ch in letters:
        tiles.append(fetch_letter_image(ch, session))
        print(ch.upper(), end=" ", flush=True)
    print()

    # Normalise all tiles to the same height
    target_h = max(t.height for t in tiles)
    normalised = []
    for tile in tiles:
        if tile.height != target_h:
            ratio = target_h / tile.height
            tile = tile.resize((int(tile.width * ratio), target_h), Image.LANCZOS)
        normalised.append(tile)

    # Composite: stitch tiles with a small gap
    gap = 6
    total_w = sum(t.width for t in normalised) + gap * (len(normalised) - 1)
    composite = Image.new("RGB", (total_w, target_h), (10, 10, 10))

    x = 0
    for tile in normalised:
        composite.paste(tile, (x, 0))
        x += tile.width + gap

    return composite


CARD_W, CARD_H = 1080, 1920
CARD_BORDER = 50  # px gap on every side


def make_card(word_img: Image.Image) -> Image.Image:
    """
    Place word_img centred on a 1080×1920 white canvas with a 50 px border.
    The image is scaled down (never up) to fit within the safe area.
    """
    safe_w = CARD_W - CARD_BORDER * 2   # 980
    safe_h = CARD_H - CARD_BORDER * 2   # 1820

    src_w, src_h = word_img.size
    scale = min(safe_w / src_w, safe_h / src_h, 1.0)  # never upscale
    new_w = int(src_w * scale)
    new_h = int(src_h * scale)

    if scale < 1.0:
        word_img = word_img.resize((new_w, new_h), Image.LANCZOS)

    canvas = Image.new("RGB", (CARD_W, CARD_H), (255, 255, 255))
    paste_x = (CARD_W - new_w) // 2
    paste_y = (CARD_H - new_h) // 2
    canvas.paste(word_img, (paste_x, paste_y))
    return canvas


def safe_name(text: str, max_len: int = 60) -> str:
    """Turn arbitrary text into a safe filename segment."""
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in text)[:max_len]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate Landsat satellite letter-art images for each word in a sentence."
    )
    parser.add_argument(
        "sentence",
        nargs="?",
        help="The sentence to process (prompted if omitted)",
    )
    args = parser.parse_args()

    sentence = args.sentence or input("Enter a sentence: ").strip()
    if not sentence:
        print("No input provided — exiting.")
        sys.exit(1)

    words = sentence.split()
    if not words:
        print("Sentence is empty — exiting.")
        sys.exit(1)

    # Output folders named after the full sentence
    base_dir = Path("output") / safe_name(sentence)
    raw_dir = base_dir / "raw"
    fmt_dir = base_dir / "formatted"
    raw_dir.mkdir(parents=True, exist_ok=True)
    fmt_dir.mkdir(parents=True, exist_ok=True)
    print(f"\nSentence  : \"{sentence}\"")
    print(f"Words     : {len(words)}")
    print(f"Raw       : {raw_dir.resolve()}")
    print(f"Formatted : {fmt_dir.resolve()}\n")

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (compatible; LandsatWordArt/1.0)",
        "Referer": "https://science.nasa.gov/specials/your-name-in-landsat/",
    })

    saved = 0
    for idx, word in enumerate(words, start=1):
        letters_only = [c for c in word if c.isalpha()]
        if not letters_only:
            print(f"  [{idx:02d}/{len(words):02d}] Skipping '{word}' — no letters\n")
            continue

        print(f"  [{idx:02d}/{len(words):02d}] '{word}'")
        try:
            img = build_word_image(word, session)
        except Exception as exc:
            print(f"    ERROR: {exc}\n")
            continue

        stem = f"{idx:02d}_{safe_name(word)}.jpg"

        raw_path = raw_dir / stem
        img.save(raw_path, "JPEG", quality=92)

        card = make_card(img)
        fmt_path = fmt_dir / stem
        card.save(fmt_path, "JPEG", quality=92)

        print(f"    raw       → {raw_path.name}  ({img.width}×{img.height}px)")
        print(f"    formatted → {fmt_path.name}  ({card.width}×{card.height}px)\n")
        saved += 1

    print(f"Done — {saved}/{len(words)} word image(s) saved.")
    print(f"  raw       : {raw_dir.resolve()}")
    print(f"  formatted : {fmt_dir.resolve()}")


if __name__ == "__main__":
    main()
