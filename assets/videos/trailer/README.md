# The oddyssey trailer

The README's trailer (`oddyssey-trailer.mp4`, 92 s, 1280x720) and the code that
generates it. The video presents oddyssey
told as Homer's Odyssey: Odysseus (your coding agent) sails the telemetry
sea, meets the monsters (bugs, bad behaviors, bad performance, blind spots)
and beats them with the signs the gods send - Loki (logs), Tempo (traces),
Mimir (metrics), Pyroscope (profiles). Instrument once, then the ODD loop:
observe, fix, verify.

Everything is drawn procedurally with Pillow, frame by frame, and piped to
ffmpeg. No video-editing library, no external assets except the repository
banner (`assets/images/banner.png`) for the closing scene.

## Requirements

- Python 3.10+ with Pillow (`pip install pillow`)
- ffmpeg on the PATH (`brew install ffmpeg`)
- numpy, for the synthesized soundtrack (`pip install numpy`)
- macOS fonts Georgia and Menlo are used when present; DejaVu is the
  fallback on Linux, and Pillow's default font last.

## Render

```bash
python3 make_video.py --scale 0.6667 --crf 30 --out oddyssey-trailer.mp4   # regenerate the committed trailer (720p, ~9 MB)
python3 make_video.py                 # 1920x1080, 30 fps -> out/oddyssey.mp4 (~30 MB)
python3 make_video.py --preview       # 960x540, 15 fps draft -> out/oddyssey-preview.mp4
python3 make_video.py --frames 16     # 16 stills to out/stills/ for a quick visual check
python3 make_video.py --music track.mp3   # use your own soundtrack instead
python3 make_video.py --no-music      # silent video
python3 make_video.py --crf 18        # near-lossless (about 2.3x bigger); default CRF 26 is ~30 MB
python3 make_music.py                 # only the soundtrack -> out/ambience.wav
```

## Soundtrack

`make_music.py` synthesizes the ambience from scratch with numpy, timed on
the scene list of `make_video.py` (no voice, no samples): a low modal drone
in D phrygian / dorian, slow chord swells that follow the story (tension on
the monsters and the battle, a D major resolution when the fix is verified
and on the outro), a plucked lyre wandering on a minor pentatonic scale
(Karplus-Strong strings), the sea as shaped noise that swells with the
storm, thunder rumbles a third of a second after each lightning flash, a
frame drum beating faster during the battle, and a bell shimmer on
"Verified". The video render calls it automatically and mixes the result
at 128 kbps AAC.

The full render takes a few minutes (each frame is drawn in pure Python).
`out/` is git-ignored; only the regenerated `oddyssey-trailer.mp4` is meant to be
committed, in the same change as the edit that made it necessary.

## Storyboard

| # | Scene | Length | What happens |
|---|-------|--------|--------------|
| 1 | Title | 8.5 s | Storm, lightning, "ODDYSSEY - Observability-Driven Development for coding agents" |
| 2 | Hero | 8.5 s | The trireme sails in, shields named Claude, Copilot, Codex, Cursor, Gemini. "What is my service really doing out there?" |
| 3 | Monsters | 12.5 s | Scylla (bugs), the Sirens (bad behaviors), Charybdis (bad performance), the Cyclops (blind spots) |
| 4 | Gods | 15 s | Loki / Tempo / Mimir / Pyroscope, each with a live widget: log scroll, trace waterfall, metric chart, flame graph. All speak OpenTelemetry, local Grafana stack or remote backend |
| 5 | Battle | 14 s | Scylla bites the agent's tool calls: 23 % in error. The four signals build finding F1 (429s from the search API, never retried), the SDD wave fixes it, verification measures 0 errors on 1,200 calls and Scylla fades |
| 6 | Loop | 15 s | Terminal typing `/odd-instrument-otel`, `/odd-observe`, `/odd-verify`; the cycle diagram with instrumentation as the one-time entry and observe -> fix -> verify as the loop; `/odd-status`, `/odd-instrument-bench`, `/odd-config` mentioned |
| 7 | Memory | 9 s | The `.odd/` tree: reports, benchmarks, decisions - committed, shared, recalled as the next baseline, append-only |
| 8 | Outro | 9.5 s | Banner with Ken Burns, "Sail on.", a timeless install line (no pinned version), repository URL |

## Editing

All scene text, durations and colours live at the top of `make_video.py`:
`GODS`, `MONSTERS`, `TERMINAL`, `TREE`, `SCENES`. Each scene is one
function `scene_<name>(t)` that returns a full frame for local time `t`;
`render_frame` stitches them with a 0.7 s crossfade. Run `--frames` after
an edit to eyeball the result before a full render.
