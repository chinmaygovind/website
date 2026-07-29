"""Synthesize King of Tokyo's UI sound stings.

The sounds are generated, not sampled - this script IS the source, and the
``.wav`` files under ``static/sounds/`` are its build output. Run it from the
``kot/`` directory to regenerate them:

    venv/bin/python tools/make_sounds.py

Only the sounds listed in ``SOUNDS`` below are written. The original five
(roll, attack, card, turn, ko) predate this script and are left alone, so
running it never changes a sound that already shipped.

Everything is mono 22050 Hz 16-bit to match the existing set, and each sting is
peak-normalized into the same range as the originals so nothing jumps out when
several play at once. Tokyo is the exception (see ``PEAK_OVERRIDE``): it is an
impact rather than a tone, so almost all its energy is in the first few
milliseconds, and peak-matching it against a sustained note would leave it
sounding much quieter than everything else.
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


class _Noise:
    """Deterministic white noise, so a rerun produces the same bytes."""

    def __init__(self, seed=1):
        self.s = seed

    def next(self):
        self.s = (1103515245 * self.s + 12345) & 0x7FFFFFFF
        return (self.s / 0x3FFFFFFF) - 1.0


def _lowpass(xs, cutoff):
    a = (2 * math.pi * cutoff / RATE) / (1 + 2 * math.pi * cutoff / RATE)
    out, y = [], 0.0
    for x in xs:
        y += a * (x - y)
        out.append(y)
    return out


def _highpass(xs, cutoff):
    lo = _lowpass(xs, cutoff)
    return [x - l for x, l in zip(xs, lo)]


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


def tokyo(dur=0.60):
    """Taking Tokyo: a monster coming through a wall.

    Three layers, because that is what an impact actually is. The CRACK is the
    masonry letting go - bright, broadband, gone in a blink. The THUD is the
    weight behind it, a pitch-dropping sine that lands a hair later and carries
    the low end. Then the RUBBLE: scattered grains of debris clattering down
    for another third of a second, which is what stops it reading as a generic
    drum hit and starts it reading as a wall.
    """
    n = int(RATE * dur)
    rng = _Noise(9001)
    out = [0.0] * n

    # 1) The crack. Hard noise burst, most of it above 1kHz so it sounds like
    #    stone splitting rather than a cymbal.
    crack = _highpass([rng.next() for _ in range(n)], 900)
    for i in range(n):
        out[i] += 1.00 * math.exp(-24.0 * (i / RATE)) * crack[i]

    # 2) The thud. A body blow: 150Hz sagging to 40Hz, slightly overdriven so
    #    it has some guts on a laptop speaker that cannot reproduce the bottom.
    for i in range(n):
        t = i / RATE
        f = 40 + 110 * math.exp(-16.0 * t)
        e = math.exp(-10.0 * t) * min(1.0, t / 0.004)
        out[i] += 0.75 * math.tanh(2.2 * e * _sine(f, t))

    # 3) The rubble. Irregular grains, deliberately unevenly spaced - evenly
    #    spaced debris sounds like a machine, not a collapsing wall.
    grain_noise = _lowpass(_highpass([rng.next() for _ in range(n)], 700), 5000)
    starts = [0.055, 0.085, 0.120, 0.150, 0.205, 0.240, 0.300, 0.345, 0.400, 0.470]
    for k, st in enumerate(starts):
        s0 = int(st * RATE)
        if s0 >= n:
            break
        amp = 0.58 * math.exp(-2.0 * st)          # later debris is quieter
        glen = int((0.035 + 0.02 * ((k * 7) % 3)) * RATE)
        for j in range(min(glen, n - s0)):
            out[s0 + j] += amp * math.exp(-55.0 * (j / RATE)) * grain_noise[s0 + j]

    # Gentle fade so the tail never clicks off.
    tail = int(0.03 * RATE)
    for i in range(max(0, n - tail), n):
        out[i] *= (n - i) / tail
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
# An impact is nearly all transient, so peak-matching it against a sustained
# tone leaves it sounding far quieter than everything else. Tokyo gets headroom.
PEAK_OVERRIDE = {"tokyo": 0.72}


def write(name, samples):
    peak = max(abs(s) for s in samples) or 1.0
    target = PEAK_OVERRIDE.get(name, PEAK)
    scale = (target * 32767) / peak
    data = b"".join(struct.pack("<h", int(max(-32767, min(32767, s * scale))))
                    for s in samples)
    path = os.path.abspath(os.path.join(OUT, name + ".wav"))
    with wave.open(path, "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(data)
    rms = math.sqrt(sum((s * scale) ** 2 for s in samples) / len(samples))
    print(f"{name:8s} {len(samples)/RATE:.3f}s  peak {target:.2f}  rms {rms/32767:.3f}")


if __name__ == "__main__":
    for name, fn in SOUNDS.items():
        write(name, fn())
