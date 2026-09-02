#!/usr/bin/env python3
"""Synthesize the ambient soundtrack of the oddyssey video - no samples, just numpy.

Ancient-Greek flavour: a low modal drone (D phrygian / dorian), slow chord
swells, a plucked lyre (Karplus-Strong) wandering on a pentatonic scale, the
sea as filtered noise that swells with the storm, thunder rumbles timed on
the lightning flashes, a frame drum during the battle, and a bright major
resolution when the fix is verified.

    python3 make_music.py            # writes out/ambience.wav for the default timeline
    python3 make_video.py            # calls this automatically (see --no-music)
"""

from __future__ import annotations

import math
import wave
from pathlib import Path

import numpy as np

SR = 44100
HERE = Path(__file__).resolve().parent

# --- pitch helpers ------------------------------------------------------------
A4 = 440.0


def hz(note: str) -> float:
    """'D3', 'Bb2', 'F#4' -> frequency in Hz."""
    names = {"C": -9, "D": -7, "E": -5, "F": -4, "G": -2, "A": 0, "B": 2}
    name, octave = note[:-1], int(note[-1])
    semis = names[name[0]]
    if len(name) > 1:
        semis += 1 if name[1] == "#" else -1
    return A4 * 2 ** ((octave - 4) + semis / 12)


# --- envelopes ----------------------------------------------------------------
def keyframes(t: np.ndarray, keys: list[tuple[float, float]]) -> np.ndarray:
    xs, ys = zip(*keys)
    return np.interp(t, xs, ys)


def adsr(n: int, attack: float, release: float, sr=SR) -> np.ndarray:
    env = np.ones(n)
    a = min(n, int(attack * sr))
    r = min(n, int(release * sr))
    if a:
        env[:a] = np.linspace(0, 1, a) ** 2
    if r:
        env[n - r :] *= np.linspace(1, 0, r) ** 2
    return env


# --- voices -------------------------------------------------------------------
def pad_note(freq: float, dur: float, detune=0.0, vibrato=0.0025) -> np.ndarray:
    """Additive organ-ish tone with slow vibrato - the drone and the chord swells."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = freq * (1 + detune) * (1 + vibrato * np.sin(2 * math.pi * 0.17 * t + freq))
    phase = 2 * math.pi * np.cumsum(f) / SR
    out = np.zeros(n)
    for k, amp in ((1, 1.0), (2, 0.45), (3, 0.22), (4, 0.1), (5, 0.05)):
        out += amp * np.sin(k * phase + k)
    return out / 1.8


def pluck(
    freq: float, dur: float, rng: np.random.Generator, decay=0.995, bright=0.5
) -> np.ndarray:
    """Karplus-Strong string, evaluated one period at a time (vectorised)."""
    period = max(2, round(SR / freq))
    buf = rng.uniform(-1, 1, period)
    # a darker excitation sounds more like gut strings on a lyre than a steel guitar
    buf = np.convolve(buf, np.ones(3) / 3, mode="same") * (1 - bright) + buf * bright
    n = int(dur * SR)
    out = np.empty(n + period)
    pos = 0
    while pos < n:
        out[pos : pos + period] = buf
        buf = decay * 0.5 * (buf + np.roll(buf, -1))
        pos += period
    return out[:n] * adsr(n, 0.002, 0.15)


def spectral_noise(
    n: int, rng: np.random.Generator, cutoff: float, slope=0.5
) -> np.ndarray:
    """White noise shaped in the frequency domain: low-pass at `cutoff`, 1/f^slope tilt."""
    white = rng.standard_normal(n)
    spec = np.fft.rfft(white)
    f = np.fft.rfftfreq(n, 1 / SR)
    shape = 1 / (1 + (f / cutoff) ** 4) / np.maximum(f, 20) ** slope
    out = np.fft.irfft(spec * shape, n)
    return out / (np.abs(out).max() + 1e-9)


# --- the score ----------------------------------------------------------------
# chords as (start, end, [notes]) - phrygian tension over a D drone, resolved in D major
def chord_plan(scene_t: dict) -> list[tuple[float, float, list[str], float]]:
    T = scene_t
    return [
        (T["title"], T["hero"], ["D3", "A3", "D4"], 0.55),
        (T["hero"], T["hero"] + 4.5, ["Bb2", "F3", "D4"], 0.5),
        (T["hero"] + 4.5, T["monsters"], ["D3", "A3", "F4"], 0.5),
        (T["monsters"], T["monsters"] + 6, ["Eb3", "G3", "Bb3"], 0.55),
        (T["monsters"] + 6, T["gods"], ["C3", "G3", "Eb4"], 0.55),
        (T["gods"], T["gods"] + 5, ["D3", "A3", "F4"], 0.5),
        (T["gods"] + 5, T["gods"] + 10, ["G2", "D3", "Bb3"], 0.5),
        (T["gods"] + 10, T["battle"], ["D3", "F3", "A3"], 0.5),
        (T["battle"], T["battle"] + 7.5, ["Eb3", "Bb3", "Eb4"], 0.6),
        (T["battle"] + 7.5, T["battle"] + 11.2, ["D3", "A3", "D4"], 0.5),
        (
            T["battle"] + 11.2,
            T["loop"],
            ["D3", "F#3", "A3", "D4"],
            0.65,
        ),  # verified: major
        (T["loop"], T["loop"] + 7, ["D3", "F3", "A3"], 0.45),
        (T["loop"] + 7, T["memory"], ["F3", "A3", "C4"], 0.45),
        (T["memory"], T["memory"] + 4.5, ["Bb2", "F3", "D4"], 0.45),
        (T["memory"] + 4.5, T["outro"], ["G2", "D3", "Bb3"], 0.45),
        (
            T["outro"],
            T["end"],
            ["D3", "F#3", "A3", "D4", "A4"],
            0.6,
        ),  # sail on: D major
    ]


LYRE_SCALE = ["D4", "F4", "G4", "A4", "C5", "D5", "F5", "G5", "A5"]


def render(
    duration: float,
    scene_starts: dict,
    flashes: list[tuple[float, float]],
    out_path: Path,
    seed=7,
) -> Path:
    """Write a stereo 16-bit WAV of `duration` seconds.

    scene_starts: {"title": 0.0, "hero": 8.5, ..., "end": total}
    flashes: [(global time, strength)] of the lightning bolts, for the thunder.
    """
    rng = np.random.default_rng(seed)
    n = int(duration * SR)
    t = np.arange(n) / SR
    T = scene_starts
    left = np.zeros(n)
    right = np.zeros(n)

    def add(start: float, sig: np.ndarray, gain_l=1.0, gain_r=1.0):
        i0 = int(start * SR)
        if i0 >= n:
            return
        seg = sig[: n - i0]
        left[i0 : i0 + len(seg)] += seg * gain_l
        right[i0 : i0 + len(seg)] += seg * gain_r

    # the storm: how rough the sea and how loud the low end, per moment of the story
    storm = keyframes(
        t,
        [
            (0, 0.85),
            (T["hero"], 0.55),
            (T["hero"] + 2, 0.3),
            (T["monsters"] - 1, 0.35),
            (T["monsters"], 0.95),
            (T["gods"] - 0.5, 0.9),
            (T["gods"] + 1.5, 0.3),
            (T["battle"] - 0.5, 0.3),
            (T["battle"] + 1, 0.8),
            (T["battle"] + 9, 0.8),
            (T["battle"] + 11.5, 0.2),
            (T["loop"], 0.15),
            (T["outro"], 0.2),
            (T["end"], 0.35),
        ],
    )

    # 1. drone: D2 + A2, two detuned voices per channel, breathing with the storm
    for note, amp in (("D2", 0.5), ("A2", 0.22), ("D3", 0.12)):
        f = hz(note)
        add(0, pad_note(f, duration, detune=-0.002) * amp, 1.0, 0.7)
        add(0, pad_note(f, duration, detune=+0.002) * amp, 0.7, 1.0)
    drone_env = 0.55 + 0.45 * storm
    left *= drone_env
    right *= drone_env

    # 2. chord swells
    for start, end, notes, amp in chord_plan(T):
        dur = end - start + 2.5  # overlap into the next chord
        for i, note in enumerate(notes):
            f = hz(note)
            sig = pad_note(f, dur, detune=0.0015 * (i - 1)) * adsr(
                int(dur * SR), 2.2, 2.5
            )
            pan = 0.5 + 0.35 * math.sin(i * 1.9)
            add(
                start,
                sig * amp * 0.28 / len(notes) ** 0.5,
                1 - pan * 0.6,
                0.4 + pan * 0.6,
            )

    # 3. lyre: short phrases in the calm scenes, lone notes in the storm
    phrases = [
        (T["hero"] + 1.5, 5, 0.9),
        (T["hero"] + 5.5, 4, 0.8),
        (T["monsters"] + 5, 1, 0.5),
        (T["monsters"] + 9, 1, 0.5),
        (T["gods"] + 1, 6, 0.85),
        (T["gods"] + 6, 5, 0.85),
        (T["gods"] + 10.5, 4, 0.8),
        (T["battle"] + 8, 3, 0.7),
        (T["battle"] + 11.4, 5, 1.0),
        (T["loop"] + 1, 5, 0.8),
        (T["loop"] + 6, 5, 0.8),
        (T["loop"] + 11, 4, 0.8),
        (T["memory"] + 1, 6, 0.8),
        (T["memory"] + 5.5, 4, 0.75),
        (T["outro"] + 0.8, 7, 0.95),
        (T["outro"] + 5.5, 3, 0.8),
    ]
    idx = 4
    for start, count, vol in phrases:
        tt = start
        for k in range(count):
            step = int(rng.integers(-2, 3))
            idx = min(len(LYRE_SCALE) - 1, max(0, idx + step))
            note = LYRE_SCALE[idx]
            sig = pluck(hz(note), 2.2, rng, decay=0.9965, bright=0.35) * 0.32 * vol
            pan = 0.35 + 0.3 * (idx / len(LYRE_SCALE))
            add(tt, sig, 1 - pan, pan)
            tt += float(rng.choice([0.45, 0.6, 0.75, 0.9, 1.2]))

    # 4. the sea: shaped noise per channel, swelling irregularly, louder in the storm
    for chan, (ph1, ph2) in ((left, (0.0, 1.3)), (right, (2.1, 0.4))):
        sea = spectral_noise(n, rng, cutoff=900, slope=0.6)
        swell = 0.55 + 0.45 * np.sin(2 * math.pi * 0.075 * t + ph1) * np.sin(
            2 * math.pi * 0.041 * t + ph2
        )
        chan += sea * swell * (0.05 + 0.28 * storm)

    # 5. thunder: a low rumble shortly after every flash
    for ft, strength in flashes:
        dur = 3.2
        m = int(dur * SR)
        tt = np.arange(m) / SR
        rumble = spectral_noise(m, rng, cutoff=140, slope=0.3)
        env = (
            (1 - np.exp(-tt / 0.04))
            * np.exp(-tt / 0.9)
            * (1 + 0.5 * np.sin(2 * math.pi * 7 * tt))
        )
        sig = rumble * env * 0.9 * strength
        pan = rng.uniform(0.3, 0.7)
        add(ft + 0.35, sig, 1 - pan * 0.5, 0.5 + pan * 0.5)

    # 6. the battle drum: a frame drum beating faster and louder until the fix lands
    beat = T["battle"] + 1.0
    k = 0
    while beat < T["battle"] + 9.2:
        m = int(0.6 * SR)
        tt = np.arange(m) / SR
        f = 58 * (1 + 1.5 * np.exp(-tt / 0.03))
        drum = np.sin(2 * math.pi * np.cumsum(f) / SR) * np.exp(-tt / 0.22)
        vol = 0.28 + 0.25 * min(1.0, k / 10)
        add(beat, drum * vol, 1.0, 1.0)
        beat += 0.8 if k < 6 else 0.6
        k += 1
    # the verified moment: a bell-like shimmer on D
    for note, amp, dl in (("D5", 0.35, 0.0), ("A5", 0.22, 0.12), ("D6", 0.16, 0.24)):
        m = int(4 * SR)
        tt = np.arange(m) / SR
        f = hz(note)
        bell = (
            np.sin(2 * math.pi * f * tt)
            + 0.4 * np.sin(2 * math.pi * f * 2.76 * tt) * np.exp(-tt / 0.5)
        ) * np.exp(-tt / 1.4)
        add(T["battle"] + 11.2 + dl, bell * amp, 0.8, 0.8)

    # master: gentle soft-clip, fades, normalise
    master = keyframes(t, [(0, 0), (1.5, 1), (duration - 3.5, 1), (duration - 0.2, 0)])
    stereo = np.stack([left, right], axis=1) * master[:, None]
    stereo = np.tanh(stereo * 1.4)
    stereo *= 0.89 / (np.abs(stereo).max() + 1e-9)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out_path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((stereo * 32767).astype(np.int16).tobytes())
    return out_path


if __name__ == "__main__":
    import make_video as mv

    starts, acc = {}, 0.0
    for name, dur, _ in mv.SCENES:
        starts[name] = acc
        acc += dur
    starts["end"] = acc
    flashes = [(starts["title"] + ft, s) for (ft, _, s) in mv.TITLE_FLASHES] + [
        (starts["monsters"] + ft, s) for (ft, _, s) in mv.MONSTER_FLASHES
    ]
    path = render(acc, starts, flashes, HERE / "out" / "ambience.wav")
    print(f"wrote {path} ({acc:.1f}s)")
