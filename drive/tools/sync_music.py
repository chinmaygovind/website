"""Put the music on the box, and prove it arrived.

The audio is the one part of Drive that is not in git (see `drive/CLAUDE.md`),
so the deploy cannot carry it: pushing to `main` resets the code on the box and
leaves `static/audio/` exactly as it found it. That is deliberate - it is what
keeps 58MB of binaries out of a public repo's permanent history - but it means
uploading is a step somebody has to remember.

**And forgetting it is silent.** A slug whose file is missing plays nothing,
which on the track looks precisely like the music being switched off. Nothing
logs, nothing 500s, the Action is green. So this does not just copy: it reads
the manifest afterwards and checks that every file it names is actually on the
box at the right size, which is the part that turns a silent failure into a
line of output.

    python tools/sync_music.py            # upload, then verify
    python tools/sync_music.py --check    # verify only, change nothing
"""

import argparse
import json
import os
import subprocess
import sys

HOST = "kotprod"                                    # the alias from ~/.ssh/config
REMOTE = "/home/ubuntu/website/drive/static/audio/"
HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "static", "audio")


def manifest_files():
    """The files the manifest says should exist, each with the slugs wanting it.

    Keyed by filename rather than by slug because the three closed circuits
    share one file - reporting `f1.mp3` missing three times would be three
    lines about one problem.
    """
    with open(os.path.join(HERE, "music.json")) as f:
        tracks = json.load(f)["tracks"]
    want = {}
    for slug, e in tracks.items():
        if e.get("file"):
            want.setdefault(e["file"], []).append(slug)
    return want


def remote_sizes(host):
    """{name: bytes} for the audio already on the box, or None if unreachable."""
    r = subprocess.run(
        ["ssh", host, "ls -l %s 2>/dev/null | awk '{print $5, $9}'" % REMOTE],
        capture_output=True, text=True)
    if r.returncode:
        print("cannot reach %s: %s" % (host, r.stderr.strip()), file=sys.stderr)
        return None
    out = {}
    for line in r.stdout.splitlines():
        parts = line.split(None, 1)
        if len(parts) == 2 and parts[1].endswith(".mp3"):
            out[parts[1]] = int(parts[0])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="verify only, upload nothing")
    ap.add_argument("--host", default=HOST)
    a = ap.parse_args()

    want = manifest_files()

    if not a.check:
        # `--times --size-only`: an mp3 that is the right size is the right file
        # here, and rsync recomputing checksums over 58MB on every run buys
        # nothing. No `--delete`: a file on the box that the manifest no longer
        # mentions is somebody mid-swap, not garbage to remove behind them.
        r = subprocess.run(["rsync", "-av", "--size-only",
                            "--include=*.mp3", "--exclude=*",
                            HERE.rstrip("/") + "/", "%s:%s" % (a.host, REMOTE)])
        if r.returncode:
            return r.returncode
        print()

    there = remote_sizes(a.host)
    if there is None:
        return 1

    missing, wrong, ok = [], [], 0
    for name, slugs in sorted(want.items()):
        local = os.path.join(HERE, name)
        if name not in there:
            missing.append((name, slugs))
        elif os.path.exists(local) and os.path.getsize(local) != there[name]:
            wrong.append((name, os.path.getsize(local), there[name]))
        else:
            ok += 1

    print("%d of %d manifest files present on %s" % (ok, len(want), a.host))
    for name, slugs in missing:
        print("  MISSING  %-16s wanted by: %s" % (name, ", ".join(slugs)))
    for name, l, r in wrong:
        print("  SIZE     %-16s local %d, box %d" % (name, l, r))
    # On the box but named by nobody: a renamed slug or a song that was swapped
    # out. Harmless - it just sits there - but worth saying, since it is dead
    # weight on a box that is short of disk and of memory.
    for name in sorted(set(there) - set(want)):
        print("  ORPHAN   %-16s on the box, in no manifest entry" % name)

    return 1 if (missing or wrong) else 0


if __name__ == "__main__":
    sys.exit(main())
