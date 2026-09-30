(function () {
  'use strict';
  if (window.cgvChat) return;

  var BASE = new URL(document.currentScript.src).origin;
  // On chat.cgovind.com itself the dock is the page: always open, no tab.
  var FULL = location.origin === BASE;
  var SITE = BASE.indexOf('cgovind.com') >= 0 ? 'https://cgovind.com' : '';
  var IO_SRC = 'https://cdn.socket.io/4.7.5/socket.io.min.js';
  var GAME_ICONS = { drive: '🏎️', kot: '👑', ers: '🃏', ttr: '🚂' };

  var S = {
    me: null, unread: 0, open: false, view: 'list', tab: 'chats',
    convs: [], conv: null, msgs: [], reads: {}, canSend: true, more: false,
    typing: {}, rooms: null, picked: {}, pickMode: 'new', muted: false, socket: null,
    toastTimer: null,
  };
  try { S.muted = localStorage.getItem('cgv.chat.muted') === '1'; } catch (e) {}

  function api(path, opts) {
    opts = opts || {};
    var init = { credentials: 'include', method: opts.method || 'GET', headers: {} };
    if (opts.method && opts.method !== 'GET') {
      init.headers['Content-Type'] = 'application/json';
      init.body = JSON.stringify(opts.body || {});
    }
    return fetch(BASE + path, init).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (j) {
        if (!r.ok) { var e = new Error(j.error || 'Something went wrong.'); e.status = r.status; throw e; }
        return j;
      });
    });
  }

  function h(tag, attrs, kids) {
    var el = document.createElement(tag);
    for (var k in (attrs || {})) {
      var v = attrs[k];
      if (v == null || v === false) continue;
      if (k === 'class') el.className = v;
      else if (k === 'text') el.textContent = v;
      else if (k.slice(0, 2) === 'on') el.addEventListener(k.slice(2), v);
      else el.setAttribute(k, v === true ? '' : v);
    }
    [].concat(kids || []).forEach(function (c) {
      if (c == null || c === false) return;
      el.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
    });
    return el;
  }

  function avatar(p, size) {
    size = size || 32;
    var st = 'width:' + size + 'px;height:' + size + 'px';
    if (p && p.avatar) return h('img', { class: 'av', src: p.avatar, alt: '', style: st });
    var name = (p && p.name) || '?';
    var hue = 0;
    for (var i = 0; i < name.length; i++) hue = (hue * 31 + name.charCodeAt(i)) % 360;
    return h('span', { class: 'av', style: st + ';background:hsl(' + hue + ',55%,45%);font-size:' + (size * 0.45) + 'px',
                       text: name.charAt(0).toUpperCase() });
  }

  function dot(p) { return h('span', { class: 'dot' + (p && p.online ? ' on' : '') }); }

  function clock(iso) {
    var d = new Date(iso);
    if (isNaN(d)) return '';
    var today = new Date().toDateString() === d.toDateString();
    var t = d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
    return today ? t : (d.getMonth() + 1) + '/' + d.getDate() + ' ' + t;
  }

  // ------------------------------------------------------------------ shell

  var host = h('div', { id: 'cgv-chat' });
  var root = host.attachShadow({ mode: 'open' });
  // Keys typed in here must never reach the page: a game reading the window's
  // keydown sees the shadow host, not an <input>, and would drive the car.
  // keyup is let through so a key held when focus arrived is still released.
  ['keydown', 'keypress'].forEach(function (t) {
    root.addEventListener(t, function (e) {
      if (e.key === 'Escape' && S.open && !FULL) { toggle(false); e.preventDefault(); }
      e.stopPropagation();
    });
  });

  root.appendChild(h('style', { text: CSS() }));
  var tab = h('button', { class: 'tab', 'aria-label': 'Chat', onclick: function () { toggle(); } },
    [h('span', { class: 'ico', text: '💬' }), h('span', { class: 'badge', hidden: true })]);
  var panel = h('div', { class: 'panel', hidden: true, role: 'dialog', 'aria-label': 'Chat' });
  var toasts = h('div', { class: 'toasts', 'aria-live': 'polite' });
  root.appendChild(tab);
  root.appendChild(panel);
  root.appendChild(toasts);

  function toggle(on) {
    S.open = on == null ? !S.open : on;
    panel.hidden = !S.open;
    tab.classList.toggle('on', S.open);
    if (S.open) {
      if (S.view === 'thread' && S.conv) openThread(S.conv.id); else showList();
    }
  }

  function setBadge(n) {
    S.unread = n;
    var b = tab.querySelector('.badge');
    b.hidden = !n;
    b.textContent = n > 99 ? '99+' : String(n);
  }

  var refreshingBadge = null;
  function refreshBadge() {
    clearTimeout(refreshingBadge);
    refreshingBadge = setTimeout(function () {
      api('/api/me').then(function (j) { setBadge(j.unread); }).catch(function () {});
    }, 300);
  }

  function header(title, back, extra) {
    return h('div', { class: 'head' }, [
      back ? h('button', { class: 'icon', 'aria-label': 'Back', onclick: back, text: '‹' }) : null,
      h('div', { class: 'title' }, title),
      extra || null,
      FULL ? null : h('button', { class: 'icon', 'aria-label': 'Close', onclick: function () { toggle(false); }, text: '×' }),
    ]);
  }

  function bell(off) {
    var d = document.createElement('div');
    d.innerHTML = '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
      + '<path d="M6 16V11a6 6 0 0 1 12 0v5l1.5 2h-15z"/><path d="M10 20.5a2 2 0 0 0 4 0"/>'
      + (off ? '<path d="M4 4l16 16"/>' : '') + '</svg>';
    return d.firstChild;
  }

  function footer() {
    return h('div', { class: 'foot' }, [
      FULL ? h('span') : h('a', { class: 'link', target: '_blank', text: 'Open full chat ↗',
        href: BASE + '/' + (S.view === 'thread' && S.conv ? '#c' + S.conv.id : '') }),
      h('button', { class: 'link snd', 'aria-label': S.muted ? 'Sound off' : 'Sound on',
        title: S.muted ? 'Sound off' : 'Sound on', onclick: function () {
        S.muted = !S.muted;
        try { localStorage.setItem('cgv.chat.muted', S.muted ? '1' : '0'); } catch (e) {}
        render();
      } }, [bell(S.muted), h('span', { text: S.muted ? 'Sound off' : 'Sound on' })]),
    ]);
  }

  function render() {
    if (!S.open) return;
    if (S.view === 'list') drawList();
    else if (S.view === 'thread') drawThread();
    else if (S.view === 'pick') drawPick();
  }

  function flash(msg) {
    var f = h('div', { class: 'flash', text: msg });
    panel.appendChild(f);
    setTimeout(function () { f.remove(); }, 3500);
  }

  // ------------------------------------------------------------------ list

  function showList() {
    S.view = 'list';
    S.conv = null;
    render();
    var load = S.tab === 'chats'
      ? api('/api/conversations').then(function (j) { S.convs = j.conversations; })
      : api('/api/friends').then(function (j) { S.friends = j.friends; });
    load.then(render).catch(function (e) { flash(e.message); });
    loadRooms();
  }

  function loadRooms() {
    return api('/api/rooms').then(function (j) { S.rooms = j.rooms; render(); return j.rooms; })
      .catch(function () { S.rooms = []; return []; });
  }

  function drawList() {
    var tabs = h('div', { class: 'tabs' }, ['chats', 'friends'].map(function (t) {
      return h('button', { class: S.tab === t ? 'on' : '', onclick: function () { S.tab = t; showList(); },
                           text: t === 'chats' ? 'Chats' : 'Friends' });
    }));
    var body = h('div', { class: 'scroll' });
    if (S.tab === 'chats') {
      body.appendChild(h('button', { class: 'wide', text: '+ New chat', onclick: function () {
        S.picked = {}; S.pickMode = 'new'; S.view = 'pick'; render();
      } }));
      if (!S.convs.length) body.appendChild(h('p', { class: 'muted', text: 'No chats yet.' }));
      S.convs.forEach(function (c) {
        var other = c.is_group ? null : c.members.filter(function (m) { return m.id !== S.me.id; })[0];
        var last = c.last;
        var preview = !last ? '' : last.kind === 'invite' ? 'Game invite' :
          last.kind === 'system' ? nameOf(c, last.sender) + ' ' + last.body : last.body;
        body.appendChild(h('button', { class: 'row' + (c.unread ? ' unread' : ''),
                                       onclick: function () { openThread(c.id); } }, [
          h('span', { class: 'who' }, [c.is_group ? h('span', { class: 'av group', text: '👥' }) : avatar(other),
                                       other ? dot(other) : null]),
          h('span', { class: 'mid' }, [h('b', { text: c.title }), h('small', { text: preview })]),
          c.unread ? h('span', { class: 'count', text: String(c.unread) }) : null,
        ]));
      });
    } else {
      var q = h('input', { class: 'search', placeholder: 'Find people to add…', type: 'search' });
      var results = h('div');
      var timer;
      q.addEventListener('input', function () {
        clearTimeout(timer);
        timer = setTimeout(function () {
          if (!q.value.trim()) { results.textContent = ''; return; }
          api('/api/people?q=' + encodeURIComponent(q.value)).then(function (j) {
            results.textContent = '';
            j.people.forEach(function (p) { results.appendChild(personRow(p)); });
            if (!j.people.length) results.appendChild(h('p', { class: 'muted', text: 'Nobody by that name.' }));
          }).catch(function () {});
        }, 250);
      });
      body.appendChild(q);
      body.appendChild(results);
      body.appendChild(h('div', { class: 'label', text: 'People you added' }));
      var friends = S.friends || [];
      if (!friends.length) body.appendChild(h('p', { class: 'muted', text: 'Search above to add people. They show up here with what they\'re playing.' }));
      friends.forEach(function (p) { body.appendChild(personRow(p)); });
    }
    panel.replaceChildren(header('Chat'), tabs, body, footer());
  }

  function personRow(p) {
    var canInvite = p.online && S.rooms && S.rooms.length;
    return h('div', { class: 'row person' }, [
      h('span', { class: 'who' }, [avatar(p), dot(p)]),
      h('span', { class: 'mid' }, [h('b', { text: p.name }), h('small', { text: p.status || '' })]),
      h('span', { class: 'acts' }, [
        canInvite ? h('button', { class: 'mini hot', text: 'Invite', onclick: function () { inviteTo(p.id); } }) : null,
        h('button', { class: 'mini', text: 'Chat', onclick: function () { openWith(p.id); } }),
        h('button', { class: 'mini', text: p.following ? 'Added' : 'Add', title: p.following ? 'Remove' : 'Add',
                      onclick: function (e) {
                        var on = !p.following;
                        api('/api/follow/' + p.id, { method: on ? 'POST' : 'DELETE' }).then(function () {
                          p.following = on; e.target.textContent = on ? 'Added' : 'Add';
                        }).catch(function (err) { flash(err.message); });
                      } }),
      ]),
    ]);
  }

  function nameOf(c, uid) {
    if (S.me && uid === S.me.id) return 'You';
    var m = (c && c.members || []).filter(function (x) { return x.id === uid; })[0];
    return m ? m.name : 'Somebody';
  }

  // ------------------------------------------------------------------ pick people

  function drawPick() {
    var q = h('input', { class: 'search', placeholder: 'Search by name…', type: 'search' });
    var results = h('div');
    var timer;
    q.addEventListener('input', function () {
      clearTimeout(timer);
      timer = setTimeout(function () {
        api('/api/people?q=' + encodeURIComponent(q.value)).then(function (j) {
          results.textContent = '';
          j.people.forEach(function (p) {
            results.appendChild(h('label', { class: 'row pick' }, [
              h('input', { type: 'checkbox', checked: !!S.picked[p.id], onchange: function (e) {
                if (e.target.checked) S.picked[p.id] = p; else delete S.picked[p.id];
                drawPickSummary();
              } }),
              h('span', { class: 'who' }, [avatar(p, 26), dot(p)]),
              h('span', { class: 'mid' }, [h('b', { text: p.name }), h('small', { text: '@' + p.username })]),
            ]));
          });
        }).catch(function () {});
      }, 200);
    });
    var summary = h('div', { class: 'picked' });
    var name = h('input', { class: 'search', placeholder: 'Group name (optional)', maxlength: 60 });
    function drawPickSummary() {
      var list = Object.keys(S.picked).map(function (k) { return S.picked[k]; });
      summary.replaceChildren(
        h('small', { class: 'muted', text: list.length ? list.map(function (p) { return p.name; }).join(', ') : 'Nobody picked yet' }),
        S.pickMode === 'new' && list.length > 1 ? name : null,
        h('button', { class: 'wide hot', disabled: !list.length, onclick: go,
                      text: S.pickMode === 'add' ? 'Add to group' : list.length > 1 ? 'Start group' : 'Start chat' }));
    }
    function go() {
      var ids = Object.keys(S.picked).map(Number);
      var req = S.pickMode === 'add'
        ? api('/api/conversations/' + S.conv.id + '/members', { method: 'POST', body: { user_ids: ids } })
        : api('/api/conversations', { method: 'POST', body: { user_ids: ids, group: ids.length > 1, name: name.value } });
      req.then(function (j) { openThread(j.conversation.id); }).catch(function (e) { flash(e.message); });
    }
    drawPickSummary();
    panel.replaceChildren(
      header(S.pickMode === 'add' ? 'Add people' : 'New chat', function () {
        if (S.pickMode === 'add') openThread(S.conv.id); else showList();
      }),
      h('div', { class: 'scroll' }, [q, results]), summary, footer());
    setTimeout(function () { q.focus(); }, 0);
  }

  // ------------------------------------------------------------------ thread

  function openWith(userId) {
    return api('/api/conversations', { method: 'POST', body: { user_ids: [userId] } })
      .then(function (j) { toggle(true); openThread(j.conversation.id); return j.conversation; })
      .catch(function (e) { toggle(true); flash(e.message); });
  }

  function openThread(cid) {
    S.view = 'thread';
    Promise.all([api('/api/conversations/' + cid), api('/api/conversations/' + cid + '/messages')])
      .then(function (r) {
        S.conv = r[0].conversation;
        S.msgs = r[1].messages; S.reads = r[1].reads; S.canSend = r[1].can_send; S.more = r[1].more;
        S.menu = false;
        render();
        markRead();
      }).catch(function (e) { flash(e.message); showList(); });
    if (S.rooms == null) loadRooms();
  }

  function markRead() {
    if (!S.open || S.view !== 'thread' || !S.conv || document.hidden) return;
    var last = S.msgs[S.msgs.length - 1];
    if (!last || (S.reads[S.me.id] || 0) >= last.id) return;
    S.reads[S.me.id] = last.id;
    api('/api/conversations/' + S.conv.id + '/read', { method: 'POST', body: { message_id: last.id } })
      .then(refreshBadge).catch(function () {});
  }

  function drawThread() {
    var c = S.conv;
    if (!c) return;
    var other = c.is_group ? null : c.members.filter(function (m) { return m.id !== S.me.id; })[0];
    var sub = c.is_group ? c.members.length + ' people' : (other ? other.status : '');
    var title = [h('b', { text: c.title }), h('small', { text: sub })];
    var menuBtn = h('button', { class: 'icon', 'aria-label': 'Options', text: '⋯',
                                onclick: function () { S.menu = !S.menu; render(); } });
    var log = h('div', { class: 'scroll log' });
    if (S.more) log.appendChild(h('button', { class: 'link center', text: 'Older messages', onclick: loadOlder }));
    var mineLast = null;
    S.msgs.forEach(function (m) {
      if (m.sender === S.me.id && m.kind !== 'system') mineLast = m;
      log.appendChild(bubble(c, m));
    });
    if (mineLast) {
      var seen = Object.keys(S.reads).filter(function (u) {
        return Number(u) !== S.me.id && S.reads[u] >= mineLast.id;
      }).length;
      if (seen) log.appendChild(h('div', { class: 'seen', text: c.is_group ? 'Seen by ' + seen : 'Seen' }));
    }
    var typers = Object.keys(S.typing).filter(function (u) { return S.typing[u] > Date.now(); });
    if (typers.length) log.appendChild(h('div', { class: 'typing',
      text: typers.map(function (u) { return nameOf(c, Number(u)); }).join(', ') + ' typing…' }));

    var parts = [header(title, showList, menuBtn)];
    if (S.menu) parts.push(threadMenu(c, other));
    parts.push(log);
    parts.push(S.canSend ? composer(c) : h('div', { class: 'foot', text: 'You can\'t send messages here.' }));
    parts.push(footer());
    panel.replaceChildren.apply(panel, parts);
    log.scrollTop = log.scrollHeight;
  }

  function threadMenu(c, other) {
    var items = [];
    if (c.is_group) {
      items.push(h('button', { text: 'Add people', onclick: function () {
        S.picked = {}; S.pickMode = 'add'; S.view = 'pick'; render();
      } }));
      var rename = h('input', { class: 'search', placeholder: 'Rename group', value: c.name || '', maxlength: 60 });
      rename.addEventListener('keydown', function (e) {
        if (e.key !== 'Enter') return;
        api('/api/conversations/' + c.id, { method: 'POST', body: { name: rename.value } })
          .then(function () { openThread(c.id); }).catch(function (err) { flash(err.message); });
      });
      items.push(rename);
      items.push(h('button', { class: 'danger', text: 'Leave group', onclick: function () {
        api('/api/conversations/' + c.id + '/leave', { method: 'POST' }).then(showList)
          .catch(function (err) { flash(err.message); });
      } }));
      c.members.forEach(function (m) {
        items.push(h('div', { class: 'row person' }, [h('span', { class: 'who' }, [avatar(m, 22), dot(m)]),
          h('span', { class: 'mid' }, [h('b', { text: m.name }), h('small', { text: m.status || '' })])]));
      });
    } else if (other) {
      items.push(h('a', { href: SITE + '/accounts/' + encodeURIComponent(other.username), text: 'View profile' }));
      items.push(h('button', { class: 'danger', text: 'Block ' + other.name, onclick: function () {
        api('/api/block/' + other.id, { method: 'POST' }).then(function () {
          flash('Blocked. They won\'t be told.'); openThread(c.id);
        }).catch(function (err) { flash(err.message); });
      } }));
      items.push(h('button', { text: 'Unblock', onclick: function () {
        api('/api/block/' + other.id, { method: 'DELETE' }).then(function () { openThread(c.id); })
          .catch(function (err) { flash(err.message); });
      } }));
    }
    return h('div', { class: 'menu' }, items);
  }

  function bubble(c, m) {
    if (m.kind === 'system') {
      return h('div', { class: 'sys', text: nameOf(c, m.sender) + ' ' + m.body });
    }
    var mine = m.sender === S.me.id;
    var inner = m.kind === 'invite' ? inviteCard(m) : h('div', { class: 'text', text: m.body });
    var meta = h('div', { class: 'meta' }, [
      c.is_group && !mine ? nameOf(c, m.sender) + ' · ' : '', clock(m.at),
      !mine ? h('button', { class: 'link report', text: 'report', title: 'Report this message',
                            onclick: function (e) { report(m, e.target); } }) : null,
    ]);
    return h('div', { class: 'msg' + (mine ? ' mine' : '') }, [inner, meta]);
  }

  function report(m, btn) {
    btn.replaceWith(h('span', { class: 'reporting' }, (function () {
      var why = h('input', { placeholder: 'What\'s wrong? (optional)', maxlength: 300 });
      var send = h('button', { class: 'mini', text: 'Send report', onclick: function () {
        api('/api/messages/' + m.id + '/report', { method: 'POST', body: { reason: why.value } })
          .then(function () { flash('Reported. Thanks.'); render(); }).catch(function (e) { flash(e.message); });
      } });
      return [why, send];
    })()));
  }

  function inviteCard(m) {
    var card = h('div', { class: 'invite' }, [h('b', { text: (GAME_ICONS[m.game] || '🎮') + ' Game invite' }),
                                              h('small', { text: 'Checking the room…' })]);
    function paint() {
      if (!card.isConnected && card._painted) return;
      api('/api/invite/' + m.id).then(function (s) {
        card._painted = true;
        if (!s.exists) {
          card.replaceChildren(h('b', { text: (GAME_ICONS[m.game] || '🎮') + ' Game invite' }),
                               h('small', { text: 'That room is gone.' }));
          return;
        }
        var what = s.status === 'waiting' ? 'in the lobby' : s.game === 'drive' ? 'racing' : 'game in progress';
        card.replaceChildren(
          h('b', { text: (GAME_ICONS[s.game] || '🎮') + ' ' + s.label }),
          h('small', { text: 'Room ' + s.code + ' · ' + s.players + '/' + s.max + ' · ' + what }),
          s.joinable ? h('a', { class: 'mini hot join', href: s.url, text: 'Join' })
                     : h('span', { class: 'mini off', text: s.players >= s.max ? 'Full' : 'Started' }));
        if (card.isConnected) setTimeout(paint, 10000);
      }).catch(function () {});
    }
    setTimeout(paint, 0);
    return card;
  }

  function loadOlder() {
    var first = S.msgs[0];
    api('/api/conversations/' + S.conv.id + '/messages?before=' + first.id).then(function (j) {
      S.msgs = j.messages.concat(S.msgs); S.more = j.more; render();
    });
  }

  var lastTyped = 0;
  function composer(c) {
    var box = h('textarea', { rows: 1, placeholder: 'Message', maxlength: 2000 });
    box.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
    });
    box.addEventListener('input', function () {
      if (S.socket && Date.now() - lastTyped > 3000) {
        lastTyped = Date.now();
        S.socket.emit('typing', { conversation_id: c.id });
      }
    });
    function send() {
      var text = box.value.trim();
      if (!text) return;
      box.value = '';
      api('/api/conversations/' + c.id + '/messages', { method: 'POST', body: { body: text } })
        .then(function (j) { addMessage(j.message); })
        .catch(function (e) { box.value = text; flash(e.message); });
    }
    var inviteBtn = h('button', { class: 'icon', title: 'Invite to your room', text: '🎮', onclick: function () {
      loadRooms().then(function (rooms) {
        if (!rooms.length) { flash('Join a room in any game first, then invite people into it.'); return; }
        if (rooms.length === 1) { sendInvite(c.id, rooms[0]); return; }
        var pick = h('div', { class: 'menu' }, rooms.map(function (r) {
          return h('button', { text: (GAME_ICONS[r.game] || '🎮') + ' ' + r.label + ' · ' + r.code + ' (' + r.players + '/' + r.max + ')',
                               onclick: function () { pick.remove(); sendInvite(c.id, r); } });
        }));
        wrap.parentNode.insertBefore(pick, wrap);
      });
    } });
    var wrap = h('div', { class: 'compose' }, [inviteBtn, box,
      h('button', { class: 'icon send', 'aria-label': 'Send', text: '➤', onclick: send })]);
    setTimeout(function () { if (window.matchMedia('(pointer: fine)').matches) box.focus(); }, 0);
    return wrap;
  }

  function sendInvite(cid, room) {
    api('/api/conversations/' + cid + '/invite', { method: 'POST', body: { game: room.game, code: room.code } })
      .then(function (j) { addMessage(j.message); }).catch(function (e) { flash(e.message); });
  }

  function inviteTo(userId) {
    return loadRooms().then(function (rooms) {
      if (!rooms.length) { toggle(true); flash('Join a room in any game first, then invite people into it.'); return; }
      return api('/api/invite', { method: 'POST', body: { user_id: userId, game: rooms[0].game, code: rooms[0].code } })
        .then(function (j) { toggle(true); openThread(j.conversation_id); })
        .catch(function (e) { toggle(true); flash(e.message); });
    });
  }

  function addMessage(m) {
    if (S.conv && m.conversation_id === S.conv.id &&
        !S.msgs.some(function (x) { return x.id === m.id; })) {
      S.msgs.push(m);
      delete S.typing[m.sender];
      render();
      markRead();
    }
  }

  // ------------------------------------------------------------------ live

  function beep() {
    if (S.muted) return;
    try {
      var ctx = beep.ctx || (beep.ctx = new (window.AudioContext || window.webkitAudioContext)());
      var o = ctx.createOscillator(), g = ctx.createGain();
      o.type = 'sine'; o.frequency.setValueAtTime(880, ctx.currentTime);
      o.frequency.exponentialRampToValueAtTime(1320, ctx.currentTime + 0.08);
      g.gain.setValueAtTime(0.0001, ctx.currentTime);
      g.gain.exponentialRampToValueAtTime(0.08, ctx.currentTime + 0.01);
      g.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.18);
      o.connect(g); g.connect(ctx.destination); o.start(); o.stop(ctx.currentTime + 0.2);
    } catch (e) {}
  }

  // A toast never takes focus and never blocks the page under it: somebody
  // holding the throttle mid-race keeps holding it. Clicking is the only way in.
  function toast(m) {
    var from = m.sender_name || 'New message';
    var text = m.kind === 'invite' ? 'invited you to play' : m.body;
    var t = h('button', { class: 'toast', tabindex: '-1', onclick: function () {
      t.remove(); toggle(true); openThread(m.conversation_id);
    } }, [h('b', { text: (m.kind === 'invite' ? (GAME_ICONS[m.game] || '🎮') + ' ' : '') + from }),
          h('span', { text: text.length > 90 ? text.slice(0, 90) + '…' : text })]);
    toasts.appendChild(t);
    while (toasts.children.length > 3) toasts.firstChild.remove();
    setTimeout(function () { t.classList.add('out'); setTimeout(function () { t.remove(); }, 400); }, 6000);
  }

  function onMessage(m) {
    var here = S.open && S.view === 'thread' && S.conv && S.conv.id === m.conversation_id && !document.hidden;
    if (S.conv && m.conversation_id === S.conv.id) addMessage(m);
    if (m.sender !== S.me.id && m.kind !== 'system') {
      if (!here) {
        var c = S.convs.filter(function (x) { return x.id === m.conversation_id; })[0];
        var named = function (conv) { m.sender_name = nameOf(conv, m.sender); toast(m); };
        if (c) named(c);
        else api('/api/conversations/' + m.conversation_id).then(function (j) { named(j.conversation); })
          .catch(function () { toast(m); });
      }
      beep();
    }
    if (S.open && S.view === 'list' && S.tab === 'chats') showList();
    refreshBadge();
  }

  function connect() {
    var go = function () {
      var s = S.socket = window.io(BASE, { withCredentials: true, transports: ['websocket', 'polling'] });
      s.on('chat_message', onMessage);
      s.on('read', function (r) {
        if (S.conv && r.conversation_id === S.conv.id) { S.reads[r.user_id] = r.last_read_id; render(); }
        if (r.user_id === S.me.id) refreshBadge();
      });
      s.on('typing', function (t) {
        S.typing[t.user_id] = Date.now() + 4000;
        if (S.conv && t.conversation_id === S.conv.id) {
          render();
          setTimeout(render, 4100);
        }
      });
    };
    if (window.io) return go();
    var tag = document.createElement('script');
    tag.src = IO_SRC;
    tag.onload = go;
    document.head.appendChild(tag);
  }

  document.addEventListener('visibilitychange', function () { if (!document.hidden) markRead(); });

  // ------------------------------------------------------------------ boot

  api('/api/me').then(function (j) {
    S.me = j.user;
    if (FULL) {
      host.className = panel.className = 'full';
      panel.classList.add('panel');
      tab.hidden = true;
      (document.querySelector('main') || document.body).appendChild(host);
      var c = /^#c(\d+)$/.exec(location.hash);
      if (c) { S.view = 'thread'; S.conv = { id: +c[1] }; }
      toggle(true);
    } else document.body.appendChild(host);
    setBadge(j.unread);
    connect();
    window.cgvChat.ready = true;
    window.dispatchEvent(new Event('cgvchat:ready'));
  }).catch(function () {});

  window.cgvChat = {
    ready: false,
    open: function (userId) { return userId ? openWith(userId) : toggle(true); },
    invite: inviteTo,
    person: function (userId) { return api('/api/people/' + userId); },
    follow: function (userId, on) { return api('/api/follow/' + userId, { method: on ? 'POST' : 'DELETE' }); },
    block: function (userId, on) { return api('/api/block/' + userId, { method: on ? 'POST' : 'DELETE' }); },
    prefs: function (policy) {
      return policy ? api('/api/prefs', { method: 'POST', body: { dm_policy: policy } }) : api('/api/me');
    },
  };

  function CSS() {
    return [
      ':host{all:initial}',
      '[hidden]{display:none!important}',
      ':host(.full){display:flex;width:100%;max-width:760px}',
      '*{box-sizing:border-box;font-family:system-ui,-apple-system,"Segoe UI",sans-serif}',
      '.tab,.panel,.toasts{--bg:#fff;--fg:#16171a;--mute:#6b6f76;--line:#e3e4e8;--soft:#f3f4f6;--hot:#2f7cf6;--mine:#2f7cf6;--mine-fg:#fff;--bad:#d93b3b}',
      '@media (prefers-color-scheme:dark){.tab,.panel,.toasts{--bg:#1b1c20;--fg:#eceef2;--mute:#9a9ea7;--line:#2e3036;--soft:#26282d;--hot:#5b9bff;--mine:#3b82f6}}',
      '.tab{position:fixed;right:0;top:var(--cgv-tab-top,67%);bottom:var(--cgv-tab-bottom,auto);z-index:2147483000;width:44px;height:48px;border:1px solid var(--line);border-right:0;border-radius:12px 0 0 12px;background:var(--bg);color:var(--fg);cursor:pointer;box-shadow:0 4px 18px rgba(0,0,0,.18);display:flex;align-items:center;justify-content:center;opacity:.85;transition:opacity .15s,transform .15s}',
      '.tab:hover,.tab.on{opacity:1;transform:translateX(-2px)}',
      '.ico{font-size:20px;line-height:1}',
      '.badge{position:absolute;top:-6px;left:-6px;min-width:20px;height:20px;padding:0 5px;border-radius:10px;background:var(--bad);color:#fff;font:700 11px/20px system-ui;text-align:center}',
      '.panel{position:fixed;right:52px;top:50%;transform:translateY(-50%);z-index:2147483001;width:360px;height:min(560px,86vh);background:var(--bg);color:var(--fg);border:1px solid var(--line);border-radius:14px;box-shadow:0 12px 40px rgba(0,0,0,.28);display:flex;flex-direction:column;overflow:hidden;font-size:14px}',
      '@media (max-width:520px){.panel{right:0;left:0;top:0;bottom:0;width:auto;height:auto;transform:none;border-radius:0}}',
      '.panel.full{position:static;transform:none;width:100%;height:auto;z-index:auto;box-shadow:0 4px 24px rgba(0,0,0,.08)}',
      '@media (max-width:520px){.panel.full{border:0;border-radius:0}}',
      '.head{display:flex;align-items:center;gap:6px;padding:10px 10px 10px 14px;border-bottom:1px solid var(--line)}',
      '.title{flex:1;min-width:0;display:flex;flex-direction:column;font-weight:700}',
      '.title small,.mid small{font-weight:400;color:var(--mute);font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}',
      'button{font:inherit;color:inherit;background:none;border:0;cursor:pointer}',
      '.icon{width:32px;height:32px;border-radius:8px;font-size:18px;display:inline-flex;align-items:center;justify-content:center}',
      '.icon:hover{background:var(--soft)}',
      '.tabs{display:flex;border-bottom:1px solid var(--line)}',
      '.tabs button{flex:1;padding:9px;color:var(--mute);border-bottom:2px solid transparent}',
      '.tabs button.on{color:var(--fg);border-color:var(--hot);font-weight:600}',
      '.scroll{flex:1;overflow-y:auto;padding:8px}',
      '.row{display:flex;align-items:center;gap:10px;width:100%;padding:8px;border-radius:10px;text-align:left}',
      'button.row:hover,label.row:hover{background:var(--soft)}',
      '.row.unread b{font-weight:800}',
      '.who{position:relative;flex:none;display:inline-flex}',
      '.av{border-radius:50%;object-fit:cover;display:inline-flex;align-items:center;justify-content:center;color:#fff;font-weight:700;flex:none}',
      '.av.group{width:32px;height:32px;background:var(--soft);font-size:16px}',
      '.dot{position:absolute;right:-1px;bottom:-1px;width:10px;height:10px;border-radius:50%;border:2px solid var(--bg);background:#9aa0a6;display:none}',
      '.dot.on{display:block;background:#2dbf5b}',
      '.mid{flex:1;min-width:0;display:flex;flex-direction:column}',
      '.mid b{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}',
      '.count{background:var(--hot);color:#fff;border-radius:10px;padding:1px 7px;font-size:12px;font-weight:700}',
      '.acts{display:flex;gap:4px}',
      '.mini{padding:4px 9px;border-radius:7px;border:1px solid var(--line);font-size:12px;white-space:nowrap;text-decoration:none;color:inherit;display:inline-block}',
      '.mini:hover{background:var(--soft)}',
      '.hot{background:var(--hot)!important;color:#fff!important;border-color:transparent}',
      '.mini.off{color:var(--mute)}',
      '.wide{width:100%;padding:9px;border-radius:9px;border:1px dashed var(--line);margin-bottom:6px;color:var(--hot);font-weight:600}',
      '.wide.hot{border-style:solid}',
      '.wide:disabled{opacity:.5;cursor:default}',
      '.search,textarea,.reporting input{width:100%;padding:8px 10px;border-radius:9px;border:1px solid var(--line);background:var(--soft);color:var(--fg);font:inherit;margin:4px 0}',
      '.label{margin:12px 4px 4px;font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--mute)}',
      '.muted{color:var(--mute);font-size:13px;padding:6px 4px}',
      '.picked{padding:8px 10px;border-top:1px solid var(--line)}',
      '.log{display:flex;flex-direction:column;gap:6px;padding:10px}',
      '.msg{max-width:82%;align-self:flex-start;display:flex;flex-direction:column}',
      '.msg.mine{align-self:flex-end;align-items:flex-end}',
      '.text{background:var(--soft);padding:7px 11px;border-radius:14px 14px 14px 4px;white-space:pre-wrap;word-break:break-word}',
      '.mine .text{background:var(--mine);color:var(--mine-fg);border-radius:14px 14px 4px 14px}',
      '.meta{font-size:11px;color:var(--mute);margin:2px 4px;display:flex;gap:6px;align-items:center}',
      '.link{color:var(--mute);text-decoration:underline;font-size:11px;padding:0}',
      '.report{opacity:0}.msg:hover .report{opacity:1}',
      '.reporting{display:flex;gap:4px;align-items:center}.reporting input{margin:0;font-size:12px;padding:3px 6px}',
      '.center{align-self:center;margin-bottom:6px}',
      '.sys{align-self:center;font-size:12px;color:var(--mute);padding:2px 8px}',
      '.seen,.typing{align-self:flex-end;font-size:11px;color:var(--mute);margin-right:4px}',
      '.typing{align-self:flex-start;font-style:italic}',
      '.invite{border:1px solid var(--line);border-radius:12px;padding:10px 12px;display:flex;flex-direction:column;gap:4px;min-width:210px;background:var(--bg)}',
      '.invite small{color:var(--mute)}',
      '.invite .join,.invite .off{align-self:flex-start;margin-top:4px;padding:5px 16px;font-weight:700}',
      '.compose{display:flex;gap:6px;align-items:flex-end;padding:8px;border-top:1px solid var(--line)}',
      '.compose textarea{margin:0;resize:none;max-height:120px}',
      '.send{color:var(--hot)}',
      '.menu{display:flex;flex-direction:column;gap:2px;padding:6px 8px;border-bottom:1px solid var(--line);max-height:45%;overflow-y:auto}',
      '.menu>button,.menu>a{text-align:left;padding:7px 8px;border-radius:8px;color:inherit;text-decoration:none}',
      '.menu>button:hover,.menu>a:hover{background:var(--soft)}',
      '.danger{color:var(--bad)!important}',
      '.foot{display:flex;justify-content:space-between;gap:8px;padding:6px 12px;border-top:1px solid var(--line);font-size:11px;color:var(--mute)}',
      '.foot .link{text-decoration:none}',
      '.snd{display:inline-flex;align-items:center;gap:5px}',
      '.flash{position:absolute;left:12px;right:12px;bottom:70px;background:var(--fg);color:var(--bg);padding:9px 12px;border-radius:9px;font-size:13px}',
      '.toasts{position:fixed;top:12px;right:12px;z-index:2147483002;display:flex;flex-direction:column;gap:8px;pointer-events:none;max-width:min(320px,calc(100vw - 24px))}',
      '.toast{pointer-events:auto;text-align:left;background:var(--bg);color:var(--fg);border:1px solid var(--line);border-left:4px solid var(--hot);border-radius:10px;padding:9px 12px;box-shadow:0 8px 24px rgba(0,0,0,.25);display:flex;flex-direction:column;gap:2px;font-size:13px;animation:in .25s ease-out;transition:opacity .4s,transform .4s}',
      '.toast span{color:var(--mute)}',
      '.toast.out{opacity:0;transform:translateX(20px)}',
      '@keyframes in{from{opacity:0;transform:translateX(20px)}}',
      '@media (prefers-reduced-motion:reduce){.toast{animation:none}}',
    ].join('\n');
  }
})();
