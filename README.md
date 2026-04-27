# landsat-music-video
Create music videos using NASA landsat imagery

## Setup
Run `source .venv/bin/activate`

## Usage

### Specific Lines of a Song
  python3 landsat_video.py \
    --song "Pink Floyd Wish You Were Here" \
    --line "How I wish how I wish you were here" \
    --line "Were just two lost souls swimming in a fish bowl"

# Full song
  python3 landsat_video.py \
    --song "Pink Floyd Wish You Were Here"

# Full song from a local file
  python3 landsat_video.py \
    --audio /path/to/song.mp3