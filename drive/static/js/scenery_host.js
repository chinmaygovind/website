/**
 * The inside of the sandbox iframe. Runs as `srcdoc`, so it has no origin.
 *
 * This file is the isolation boundary and it is deliberately almost empty: it
 * owns no geometry, no API and no judgement about what the code it runs is
 * allowed to produce. All it does is hold a Worker at arm's length and kill it
 * on a stopwatch. Everything that decides what scenery may be lives in
 * `scenery_worker.js`, and everything that decides whether the result is
 * acceptable runs back in the parent on numbers.
 *
 * Why an iframe at all, when the Worker is already a separate thread: a Worker
 * created from the main page inherits the *page's* origin, so a stranger's
 * scenery could `fetch('/api/...')` with the reader's cookies attached. The
 * parent creates this frame with `sandbox="allow-scripts"` and deliberately
 * without `allow-same-origin`, which makes its origin opaque - nobody's - and a
 * Worker started in here inherits that. There are no cookies to send, no
 * storage to read, and a request back to the site is a credential-less
 * cross-origin request the site does not answer.
 */
(function () {
  let workerSrc = null, worker = null, timer = null, job = null;

  function reply(msg) { parent.postMessage(msg, '*'); }

  function kill() {
    if (worker) { worker.terminate(); worker = null; }
    if (timer) { clearTimeout(timer); timer = null; }
  }

  window.addEventListener('message', (e) => {
    const m = e.data || {};
    if (m.type === 'boot') {
      workerSrc = m.worker;
      reply({ type: 'ready' });
      return;
    }
    if (m.type !== 'run' || !workerSrc) return;
    // One run at a time, newest wins: the editor rebuilds on a keystroke and
    // the answer wanted is the current one, not all of them.
    kill();
    job = m.id;
    const url = URL.createObjectURL(new Blob([workerSrc], {
      type: 'text/javascript',
    }));
    try {
      worker = new Worker(url);
    } catch (err) {
      reply({ type: 'done', id: job, result: {
        ok: false, kind: 'host', error: 'The sandbox would not start: ' + err }});
      return;
    }
    URL.revokeObjectURL(url);
    const id = job;
    worker.onmessage = (ev) => { kill(); reply({ type: 'done', id, result: ev.data }); };
    worker.onerror = (ev) => {
      kill();
      // A syntax error surfaces here rather than as a thrown exception inside
      // the worker, because the code never got as far as running.
      reply({ type: 'done', id, result: {
        ok: false, kind: 'syntax', name: 'SyntaxError',
        error: ev.message || 'The sandbox could not parse this.',
        stack: (ev.filename ? 'line ' + ev.lineno : ''),
      }});
      ev.preventDefault();
    };
    // The hard wall. The worker has its own softer deadline so a merely slow
    // run gets a message it can act on; this is for the case where it cannot
    // reach that check at all, which is what an infinite loop with no calls in
    // it looks like.
    timer = setTimeout(() => {
      kill();
      reply({ type: 'done', id, result: {
        ok: false, kind: 'timeout',
        error: 'This ran for longer than two and a half seconds and was '
             + 'stopped. A loop with no exit is the usual cause; a loop over '
             + 'every station inside a loop over every station is the next.',
      }});
    }, 2500);
    worker.postMessage(m.job);
  });
  reply({ type: 'hello' });
})();
