"""Synthesize King of Tokyo's UI sound stings.

The sounds are generated, not sampled - this script IS the source, and the
``.wav`` files under ``static/sounds/`` are its build output. Run it from the
``kot/`` directory to regenerate them:

    venv/bin/python tools/make_sounds.py

Only the sounds listed in ``SOUNDS`` below are written. The original five
(roll, attack, card, turn, ko) predate this script and are left alone, so
running it never changes a sound that already shipped.

Everything is mono 22050 Hz 16-bit to match the existing set, and each sting is
normalized to a peak in the same 0.5-0.6 range so nothing jumps out when the
mixer plays several at once.
"""

import math
import os
import struct
import wave

RATE = 22050
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "static", "sounds")


def _env(i, n, attack=0.01, decay=3.0):
    """Click-free envelope: short linear attack, exponential decay."""
    t = i / n
    a = min(1.0, (i / RATE) / attack) if attack > 0 else 1.0
    return a * math.exp(-decay * t)


def _sine(f, t):
    return math.sin(2 * math.pi * f * t)


def _square(f, t):
    return 1.0 if math.sin(2 * math.pi * f * t) >= 0 else -1.0


def _saw(f, t):
    return 2.0 * ((f * t) % 1.0) - 1.0


def vp(dur=0.26):
    """Points scored: a bright major arpeggio climbing to a little peak."""
    n = int(RATE * dur)
    notes = [1046.5, 1318.5, 1568.0]        # C6 E6 G6
    step = n // len(notes)
    out = [0.0] * n
    for k, f in enumerate(notes):
        start = k * step
        for i in range(start, n):
            j = i - start
            t = j / RATE
            e = _env(j, n - start, attack=0.004, decay=5.0)
            # a touch of the octave keeps it bright rather than flute-like
            out[i] += e * (0.75 * _sine(f, t) + 0.18 * _sine(f * 2, t))
    return out


def energy(dur=0.16):
    """An electric cube: a square-wave zap sweeping down, with a little grit."""
    n = int(RATE * dur)
    out = []
    seed = 12345
    for i in range(n):
        t = i / RATE
        f = 1400 * math.exp(-7.0 * t) + 320          # fast downward sweep
        e = _env(i, n, attack=0.002, decay=6.0)
        seed = (1103515245 * seed + 12345) & 0x7FFFFFFF
        noise = (seed / 0x3FFFFFFF) - 1.0
        out.append(e * (0.62 * _square(f, t) + 0.12 * noise))
    return out


def tokyo(dur=0.44):
    """Taking the city: a two-step fanfare in fifths, with low body under it."""
    n = int(RATE * dur)
    pairs = [(392.0, 587.3), (523.3, 784.0)]         # G4+D5 then C5+G5
    step = n // len(pairs)
    out = [0.0] * n
    for k, (lo, hi) in enumerate(pairs):
        start = k * step
        for i in range(start, n):
            j = i - start
            t = j / RATE
            e = _env(j, n - start, attack=0.008, decay=3.4)
            out[i] += e * (0.30 * _saw(lo, t) + 0.30 * _sine(hi, t)
                           + 0.22 * _sine(lo / 2, t))
    return out


def heal(dur=0.30):
    """Healing: a soft pair of tones gliding upward. Warm, no edge."""
    n = int(RATE * dur)
    out = []
    f0, f1 = 660.0, 1174.7                            # E5 gliding to D6
    for i in range(n):
        t = i / RATE
        g = t / dur
        f = f0 + (f1 - f0) * (g * g)                  # ease-in glide
        e = _env(i, n, attack=0.02, decay=2.6)
        out.append(e * (0.60 * _sine(f, t) + 0.22 * _sine(f * 1.5, t)))
    return out


SOUNDS = {"vp": vp, "energy": energy, "tokyo": tokyo, "heal": heal}
PEAK = 0.58            # matches roll/turn/ko, which sit at 0.60-0.65


def write(name, samples):
    peak = max(abs(s) for s in samples) or 1.0
    scale = (PEAK * 32767) / peak
    data = b"".join(struct.pack("<h", int(max(-32767, min(32767, s * scale))))
                    for s in samples)
    path = os.path.abspath(os.path.join(OUT, name + ".wav"))
    with wave.open(path, "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(data)
    rms = math.sqrt(sum((s * scale) ** 2 for s in samples) / len(samples))
    print(f"{name:8s} {len(samples)/RATE:.3f}s  peak {PEAK:.2f}  rms {rms/32767:.3f}")


if __name__ == "__main__":
    for name, fn in SOUNDS.items():
        write(name, fn())
