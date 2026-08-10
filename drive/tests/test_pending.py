"""A guest's times, kept until there is an account to put them on.

`pending.js` is the only thing standing between a good lap set by somebody
without an account and that lap being thrown away, and it runs on pages the
game code never touches - so it is worth testing on its own rather than
noticing later that nothing was ever saved.

The real file is run in QuickJS against a stub browser: a localStorage that is
a dictionary, a `fetch` the test decides the answer of, and a record of every
request made. `flush` is async, so each test pumps the job queue until it is
idle, the same way a browser would.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from jsrt import HAVE_QUICKJS

pytestmark = pytest.mark.skipif(not HAVE_QUICKJS, reason="quickjs not installed")

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "static", "js", "pending.js")

STUB = r"""
var store = {};
var localStorage = {
  getItem: (k) => (k in store ? store[k] : null),
  setItem: (k, v) => { store[k] = String(v); },
  removeItem: (k) => { delete store[k]; },
};
// Every request made, and what the next one should answer with.
var sent = [];
var replies = [];
function fetch(url, opts) {
  sent.push({ url, body: JSON.parse(opts.body) });
  const r = replies.shift() || { status: 200, json: { ok: true, stored: true, improved: true } };
  if (r.throw) return Promise.reject(new Error('offline'));
  return Promise.resolve({
    status: r.status,
    json: () => Promise.resolve(r.json),
  });
}
var shown = [];
var document = {
  readyState: 'complete',
  addEventListener: function () {},
  createElement: () => ({
    className: '', innerHTML: '', classList: { add: function () {}, remove: function () {} },
    remove: function () {},
  }),
  body: { appendChild: (el) => shown.push(el) },
};
function requestAnimationFrame(f) { f(); }
function setTimeout(f, ms) { return 0; }
var window = { DRIVE_USER: false, DRIVE_TRACK_NAMES: { sunrise: 'Sunrise Circuit' } };
"""

RUN = r"""
function pending() {
  const raw = localStorage.getItem('drive.pending');
  return raw ? JSON.parse(raw) : {};
}
function slugs() { return Object.keys(pending()).sort().join(','); }
function ghost(n) {
  const out = [];
  for (let i = 0; i < n; i++) out.push([i * 1.5, 0.45, 0, 0, 0, 0, 1]);
  return out;
}
function run(track, ms, frames) {
  return { track, time_ms: ms, splits: [ms / 2], ghost: ghost(frames || 4), distance: 100,
           verify: { i: [1, 480], a: [[0, 1, 2, 3, 0, 0, 0, 1, 0, 0, 0, 0]] } };
}
"""


def ctx():
    import quickjs
    c = quickjs.Context()
    c.eval(STUB + open(SRC).read() + RUN)
    return c


def pump(c):
    """Run queued promise jobs to completion, as a browser's loop would."""
    for _ in range(1000):
        if not c.execute_pending_job():
            return
    raise AssertionError("promise jobs never settled")




def do(c, script):
    """Run a script, then let everything it started settle.

    Separate from reading the result, because `flush` is async: asserting in the
    same statement that called it would be asserting about the moment before the
    requests came back, which is not the moment anyone cares about.
    """
    c.eval("(function(){" + script + "})()")
    pump(c)


def q(c, expr):
    """Ask the stub browser a question."""
    return c.eval("(function(){ return " + expr + "; })()")


# ---------------------------------------------------------------------------
# Keeping a run
# ---------------------------------------------------------------------------

def test_a_guest_run_is_kept():
    c = ctx()
    do(c, "window.DrivePending.save(run('sunrise', 20000));")
    assert q(c, "slugs()") == "sunrise"


def test_only_the_best_run_per_track_is_kept():
    """Kept per track rather than one at a time: a guest who drives five tracks
    and then signs up should not lose four of them."""
    c = ctx()
    do(c, """
      window.DrivePending.save(run('sunrise', 22000));
      window.DrivePending.save(run('sunrise', 19000));
      window.DrivePending.save(run('sunrise', 25000));
      window.DrivePending.save(run('twist', 30000));
    """)
    assert q(c, "slugs()") == "sunrise,twist"
    assert q(c, "pending()['sunrise'].time_ms") == 19000


def test_the_replay_is_kept_with_the_time():
    """A time with no replay is refused by /api/run, so keeping one without the
    other would mean keeping something that can never be submitted."""
    c = ctx()
    do(c, "window.DrivePending.save(run('sunrise', 20000, 6));")
    assert q(c, "[pending()['sunrise'].ghost.length, pending()['sunrise'].splits.length,"
                " pending()['sunrise'].distance].join(',')") == "6,1,100"


def test_the_replay_is_rounded_but_not_mangled():
    c = ctx()
    do(c, """
      window.DrivePending.save({ track: 'sunrise', time_ms: 20000, splits: [],
        ghost: [[1.234567, 2.345678, 3.456789, 0.1234567, 0, 0, 0.9876543]] });
    """)
    f = q(c, "pending()['sunrise'].ghost[0].join(',')").split(",")
    x, y, w = float(f[0]), float(f[1]), float(f[6])
    # Centimetres, and the quaternion to ~4dp: exactly what the server quantises
    # to anyway, so storing it smaller loses nothing.
    assert abs(x - 1.234567) < 0.01 and abs(y - 2.345678) < 0.01
    assert abs(w - 0.9876543) < 0.001


# ---------------------------------------------------------------------------
# Handing them over
# ---------------------------------------------------------------------------

def test_nothing_is_sent_while_logged_out():
    """Otherwise every page load would post runs that have nowhere to go."""
    c = ctx()
    do(c, "window.DrivePending.save(run('sunrise', 20000)); window.DrivePending.flush();")
    assert q(c, "sent.length") == 0
    assert q(c, "slugs()") == "sunrise", "and it is still there for when you do"


def test_logging_in_hands_every_kept_run_over():
    c = ctx()
    do(c, """
      window.DrivePending.save(run('sunrise', 20000));
      window.DrivePending.save(run('twist', 30000));
      window.DRIVE_USER = true;
      window.DrivePending.flush();
    """)
    assert q(c, "sent.map(s => s.body.track).sort().join(',')") == "sunrise,twist"
    # Drained, so the next page load is quiet rather than sending them again.
    assert q(c, "slugs()") == ""


def test_what_is_sent_is_the_whole_run():
    """The ordinary endpoint with the ordinary payload - a lap saved this way is
    not a second-class time, it is the same submission made later."""
    c = ctx()
    do(c, """
      window.DrivePending.save(run('sunrise', 20000, 5));
      window.DRIVE_USER = true;
      window.DrivePending.flush();
    """)
    assert q(c, "[sent[0].url, sent[0].body.track, sent[0].body.time_ms,"
                " sent[0].body.ghost.length, sent[0].body.splits.length].join('|')"
             ) == "/api/run|sunrise|20000|5|1"


def test_the_evidence_travels_with_the_lap():
    """A kept lap carries what the driver did at every step, not only the replay.

    Without it a guest's best lap arrives at `/api/run` at login unverifiable,
    and if it is quick enough to place it is refused rather than stored - so the
    one thing this file exists to protect would be lost at the last moment.
    """
    c = ctx()
    do(c, """
      window.DrivePending.save(run('sunrise', 20000, 5));
      window.DRIVE_USER = true;
      window.DrivePending.flush();
    """)
    assert q(c, "JSON.stringify(sent[0].body.verify.i)") == "[1,480]"
    assert q(c, "sent[0].body.verify.a.length") == 1


def test_a_full_quota_costs_the_evidence_and_not_the_lap():
    """The evidence is most of a kept run's size and is read for almost none of
    them, so when there is no room for both, the time is what survives.

    Dropping the whole write - which is what used to happen - loses laps that
    would have been accepted, to protect evidence that most of them never needed.
    """
    c = ctx()
    # A quota that refuses anything with an input stream in it.
    c.eval("""
      localStorage.setItem = function (k, v) {
        if (v.indexOf('"verify":{') >= 0) throw new Error('QuotaExceededError');
        store[k] = String(v);
      };
    """)
    do(c, "window.DrivePending.save(run('sunrise', 20000, 5));")
    assert q(c, "slugs()") == "sunrise"
    assert q(c, "pending()['sunrise'].time_ms") == 20000
    assert q(c, "pending()['sunrise'].verify") is None


def test_a_rejected_run_is_dropped_rather_than_retried_forever():
    """The server has decided the replay does not hold up. Asking again on every
    page load for the rest of time will not change its mind."""
    c = ctx()
    do(c, """
      replies.push({ status: 400, json: { ok: false, error: 'no replay' } });
      window.DrivePending.save(run('sunrise', 20000));
      window.DRIVE_USER = true;
      window.DrivePending.flush();
    """)
    assert q(c, "sent.length") == 1
    assert q(c, "slugs()") == ""


def test_a_failed_request_keeps_the_run_for_next_time():
    """Offline is not a verdict - surviving it is the whole point of this."""
    c = ctx()
    do(c, """
      replies.push({ throw: true });
      window.DrivePending.save(run('sunrise', 20000));
      window.DRIVE_USER = true;
      window.DrivePending.flush();
    """)
    assert q(c, "sent.length") == 1
    assert q(c, "slugs()") == "sunrise"


def test_a_saved_time_is_announced():
    """Times appearing on a leaderboard with no explanation are a mystery."""
    c = ctx()
    do(c, """
      replies.push({ status: 200, json: { ok: true, stored: true, improved: true, rank: 3 } });
      window.DrivePending.save(run('sunrise', 20000));
      window.DRIVE_USER = true;
      window.DrivePending.flush();
    """)
    assert q(c, "shown.length") == 1
    html = q(c, "shown[0].innerHTML")
    assert "Sunrise Circuit" in html and "#3" in html


def test_a_run_that_did_not_beat_your_pb_is_cleared_quietly():
    """It was submitted and counted; there is just nothing to announce."""
    c = ctx()
    do(c, """
      replies.push({ status: 200, json: { ok: true, stored: true, improved: false } });
      window.DrivePending.save(run('sunrise', 20000));
      window.DRIVE_USER = true;
      window.DrivePending.flush();
    """)
    assert q(c, "slugs()") == ""
    assert q(c, "shown.length") == 0
