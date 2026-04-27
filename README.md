# landsat-music-video
Create music videos using NASA landsat imagery

## Usage

### Generate specific words
`./run.sh words "hello world"`

### Specific Lines of a Song
```
  ./run.sh video \
    --song "Pink Floyd Wish You Were Here" \
    --line "How I wish how I wish you were here"
```

### Full song
`/run.sh video --song "Pink Floyd Wish You Were Here"`

### Full song from a local file
`/run.sh video --audio /path/to/song.mp3`

## AI Disclosure
This project was made with the help of Claude Code