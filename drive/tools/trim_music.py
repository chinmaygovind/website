"""Cut a song down to the part that loops, and encode it small.

The music arrives as whole uploads - a three minute track at 280kbps, or in one
case thirty minutes of the same theme repeated. Neither is what the game wants.
A song under a race wants **one section at full level with no intro build and no
fade-out**, because `MusicPlayer` loops by crossfading the tail back into the
head: a fade-out crossfaded into a cold intro is the music dropping away every
time round, which is exactly what the crossfade exists to avoid.

So this finds the sustained full-level region, cuts to it, and re-encodes. What
comes out is `in`/`out` already applied, which is why the manifest entries for a
trimmed file need neither - they are there for fine-tuning afterwards.

**No fades are applied on the way out, deliberately.** The edges want to be at
full level for the crossfade to join them; a file that fades at both ends fades
twice in the game.

    python tools/trim_music.py in.mp3 out.mp3 [--seconds 180] [--bitrate 128k]
"""

import argparse
import json
import os
import re
import subprocess
import sys

# How far below the song's own loud level still counts as "playing". A fade
# passes through this on its way down, which is what makes it the edge.
DROP_DB = 8.0
# Analysis granularity. A second is short enough to place a cut on and long
# enough not to be fooled by one quiet bar.
WIN = 1.0


def rms_per_second(path):
    """[(t, dBFS)] for the whole file, via one ffmpeg pass."""
    out = subprocess.run(
        ["ffmpeg", "-nostdin", "-hide_banner", "-nostats", "-i", path,
         "-af", "aresample=8000,asetnsamples=%d,astats=metadata=1:reset=1,"
                "ametadata=print:key=lavfi.astats.Overall.RMS_level" % int(8000 * WIN),
         "-f", "null", "-"],
        capture_output=True, text=True).stderr
    times = [float(x) for x in re.findall(r"pts_time:([\d.]+)", out)]
    lvls = [float(x) for x in re.findall(r"RMS_level=(-?[\d.]+)", out)]
    # astats emits 0.0 for the empty frames past the end; they are not silence,
    # they are nothing, and treating them as full level would extend the song.
    return [(t, l) for t, l in zip(times, lvls) if l < -0.001]


def loud_window(levels):
    """First and last second at full level - i.e. the song without its edges."""
    if not levels:
        return None
    loud = sorted((l for _, l in levels), reverse=True)
    # The 75th percentile of the loudest half, so one clipped peak cannot set
    # the reference for the whole song.
    ref = loud[len(loud) // 4]
    floor = ref - DROP_DB
    inside = [t for t, l in levels if l >= floor]
    return (inside[0], inside[-1]) if inside else None


def loop_period(levels, lo=20):
    """The repeat period of a file that is one theme over and over, or None.

    A thirty minute upload of a game theme is the same eighty seconds played
    twenty times, and cutting an arbitrary three minutes out of it lands the
    seam mid-phrase. Correlating the loudness envelope against itself finds the
    real period, and cutting exactly one of them makes the loop seamless before
    the crossfade has done anything - the end of a period *is* the start of the
    next one.

    Only trusted on a clear peak. A through-composed song has no period, and
    inventing one for it would be worse than not looking.
    """
    env = [l for _, l in levels]
    n = len(env)
    if n < lo * 4:
        return None
    m = sum(env) / n
    x = [v - m for v in env]
    den = sum(v * v for v in x)
    if den <= 0:
        return None
    best, at = 0.0, None
    for lag in range(lo, n // 3):
        s = sum(x[i] * x[i + lag] for i in range(n - lag))
        # Scaled for the shorter overlap at long lags, or every long lag loses.
        score = s / den * (n / (n - lag))
        if score > best:
            best, at = score, lag
    # 0.75 is well clear of what an unrepeated song scores and well under what a
    # genuine repeat does - the Gauntlet upload came out at 0.92.
    return at if best >= 0.75 else None


def duration(path):
    out = subprocess.run(["ffprobe", "-v", "quiet", "-print_format", "json",
                          "-show_format", path], capture_output=True, text=True).stdout
    return float(json.loads(out)["format"]["duration"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--seconds", type=float, default=None,
                    help="cap the length; a long upload is the same loop over and over")
    ap.add_argument("--bitrate", default="128k")
    ap.add_argument("--start", type=float, default=None,
                    help="cut from here instead of the detected edge, in seconds")
    ap.add_argument("--end", type=float, default=None,
                    help="cut to here instead of the detected edge, in seconds")
    ap.add_argument("--auto-loop", action="store_true",
                    help="detect the repeat period and cut exactly one of it")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    total = duration(a.src)
    levels = rms_per_second(a.src)
    win = loud_window(levels)
    if not win:
        print("%s: could not read a level from this file" % a.src, file=sys.stderr)
        return 1
    start, end = win
    # `end` is the last second that was loud, so the audio runs to the end of it.
    end = min(end + WIN, total)

    # A hand-written range beats the detector: the edges it finds are where the
    # sound starts and stops, which is not always where the *music* does - an
    # extended upload played twice through is at full level across the join.
    if a.start is not None:
        start = a.start
    if a.end is not None:
        end = min(a.end, total)

    capped = ""
    if a.auto_loop and a.end is None:
        period = loop_period(levels)
        if period:
            end = min(start + period, total)
            capped = "  (one %ds loop)" % period
        else:
            capped = "  (no repeat found)"
    if a.seconds and end - start > a.seconds:
        end = start + a.seconds
        capped = "  (capped)"

    print("%-16s %6.1fs -> %5.1f..%-6.1f = %5.1fs%s"
          % (os.path.basename(a.src), total, start, end, end - start, capped))
    if a.dry_run:
        return 0

    # `-ss` before `-i` seeks by keyframe and is fast; the re-encode below makes
    # it sample-accurate anyway. No `-af afade`: see the module docstring.
    # `-nostdin` on both calls: without it ffmpeg consumes whatever is feeding a
    # `while read` loop and the batch quietly processes half its list.
    r = subprocess.run(
        ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
         "-ss", "%.3f" % start, "-t", "%.3f" % (end - start), "-i", a.src,
         "-map", "0:a:0", "-c:a", "libmp3lame", "-b:a", a.bitrate,
         "-map_metadata", "-1", a.dst])
    if r.returncode:
        return r.returncode
    print("%s %.1fMB" % (" " * 16, os.path.getsize(a.dst) / 1e6))
    return 0


if __name__ == "__main__":
    sys.exit(main())
