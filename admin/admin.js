(function () {
  'use strict';

  var REPO = 'tkuodisx-ops/remaster';
  var BRANCH = 'main';
  var API = 'https://api.github.com';
  var TOKEN_KEY = 'rm_admin_token';

  var ICONS = ['desktop', 'laptop', 'temperature-arrow-down', 'stethoscope', 'screwdriver-wrench', 'hard-drive',
    'memory', 'microchip', 'wifi', 'shield-halved', 'bolt', 'mobile-screen', 'print', 'fan', 'database',
    'battery-full', 'keyboard', 'tv', 'gamepad', 'plug', 'virus-slash', 'cloud', 'headset', 'wrench'];
  var CATS = ['Patarimai', 'Naujienos', 'Kita'];

  var COLS = {
    straipsniai: { dir: 'straipsniai', label: 'Straipsniai', one: 'straipsnį', hasDate: true, hasCat: true },
    puslapiai: { dir: 'puslapiai', label: 'Puslapiai', one: 'puslapį', hasDate: false, hasCat: false }
  };

  var LT = { 'ą': 'a', 'č': 'c', 'ę': 'e', 'ė': 'e', 'į': 'i', 'š': 's', 'ų': 'u', 'ū': 'u', 'ž': 'z' };

  var token = null;
  try { token = localStorage.getItem(TOKEN_KEY); } catch (e) { }

  var appEl = document.getElementById('app');
  var toastEl = document.getElementById('toast');
  var viewEl = null;

  // ---------- pagalbinės ----------
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function slugify(t) {
    t = String(t).toLowerCase().replace(/[ąčęėįšųūž]/g, function (c) { return LT[c]; });
    t = t.replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
    return t || 'irasas';
  }
  function today() {
    var d = new Date();
    return d.getFullYear() + '-' + ('0' + (d.getMonth() + 1)).slice(-2) + '-' + ('0' + d.getDate()).slice(-2);
  }
  function b64enc(str) {
    var bytes = new TextEncoder().encode(str), bin = '', i;
    for (i = 0; i < bytes.length; i += 8192) {
      bin += String.fromCharCode.apply(null, bytes.subarray(i, i + 8192));
    }
    return btoa(bin);
  }
  function b64dec(b64) {
    var bin = atob(String(b64).replace(/\n/g, ''));
    var bytes = new Uint8Array(bin.length), i;
    for (i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    return new TextDecoder().decode(bytes);
  }
  function encPath(p) { return p.split('/').map(encodeURIComponent).join('/'); }
  var toastTimer;
  function toast(msg, type) {
    var icon = type === 'err' ? 'triangle-exclamation' : (type === 'ok' ? 'circle-check' : 'circle-info');
    toastEl.className = 'show ' + (type || '');
    toastEl.innerHTML = '<i class="fa-solid fa-' + icon + '"></i> ' + esc(msg);
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { toastEl.className = ''; }, type === 'err' ? 6000 : 3500);
  }
  function loading(el, text) {
    el.innerHTML = '<div class="empty"><span class="spin"></span>' + esc(text || 'Kraunama...') + '</div>';
  }
  function catClass(s) {
    var h = 0, i;
    for (i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0;
    return 'c' + (h % 6);
  }

  // ---------- GitHub API ----------
  function api(method, path, body) {
    var url = API + '/repos/' + REPO + path;
    if (method === 'GET') url += (path.indexOf('?') > -1 ? '&' : '?') + 'ref=' + BRANCH + '&_=' + Date.now();
    return fetch(url, {
      method: method,
      headers: { 'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.github+json' },
      body: body ? JSON.stringify(body) : undefined
    }).then(function (r) {
      if (r.status === 404 && method === 'GET') return null;
      return r.json().then(function (j) {
        if (r.status === 401) { logout(true); throw new Error('Raktas nebegalioja. Prisijunkite iš naujo.'); }
        if (!r.ok) throw new Error(j && j.message ? j.message : 'Klaida ' + r.status);
        return j;
      });
    });
  }
  function getFile(path) {
    return api('GET', '/contents/' + encPath(path)).then(function (j) {
      if (!j || Array.isArray(j)) return null;
      return { sha: j.sha, text: b64dec(j.content) };
    });
  }
  function listDir(dir) {
    return api('GET', '/contents/' + encPath(dir)).then(function (j) { return Array.isArray(j) ? j : []; });
  }
  function putFile(path, contentB64, message) {
    return api('GET', '/contents/' + encPath(path)).then(function (cur) {
      var body = { message: message, content: contentB64, branch: BRANCH };
      if (cur && cur.sha) body.sha = cur.sha;
      return api('PUT', '/contents/' + encPath(path), body);
    });
  }
  function saveText(path, text, message) { return putFile(path, b64enc(text), message); }
  function deleteFile(path, message) {
    return api('GET', '/contents/' + encPath(path)).then(function (cur) {
      if (!cur) return null;
      return api('DELETE', '/contents/' + encPath(path), { message: message, sha: cur.sha, branch: BRANCH });
    });
  }
  function loadJson(path, def) {
    return getFile(path).then(function (f) {
      if (!f) return def;
      try { return JSON.parse(f.text); } catch (e) { return def; }
    });
  }

  // ---------- nuotraukos ----------
  function resizeImage(file, max) {
    return new Promise(function (res, rej) {
      var url = URL.createObjectURL(file), img = new Image();
      img.onload = function () {
        var w = img.naturalWidth, h = img.naturalHeight, s = Math.min(1, max / Math.max(w, h));
        var c = document.createElement('canvas');
        c.width = Math.round(w * s); c.height = Math.round(h * s);
        var ctx = c.getContext('2d');
        ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, c.width, c.height);
        ctx.drawImage(img, 0, 0, c.width, c.height);
        URL.revokeObjectURL(url);
        var d = c.toDataURL('image/jpeg', 0.82);
        res({ base64: d.split(',')[1], dataUrl: d });
      };
      img.onerror = function () { rej(new Error('Nepavyko perskaityti nuotraukos')); };
      img.src = url;
    });
  }
  function uploadImage(file) {
    var base = file.name.replace(/\.[^.]+$/, '');
    return resizeImage(file, 1600).then(function (r) {
      var name = Date.now().toString(36) + '-' + slugify(base) + '.jpg';
      return putFile('nuotraukos/' + name, r.base64, 'Nuotrauka: ' + name).then(function () {
        return { name: name, dataUrl: r.dataUrl };
      });
    });
  }

  // ---------- Markdown meta ----------
  function parseMd(text) {
    var m = text.replace(/\r\n/g, '\n').match(/^---\s*\n([\s\S]*?)\n---\s*\n?([\s\S]*)$/);
    var meta = {}, body = text;
    if (m) {
      m[1].split('\n').forEach(function (l) {
        var i = l.indexOf(':');
        if (i > 0) meta[l.slice(0, i).trim().toLowerCase()] = l.slice(i + 1).trim().replace(/^"(.*)"$/, '$1');
      });
      body = m[2];
    }
    return { meta: meta, body: body.replace(/^\n+/, '') };
  }
  function buildMd(meta, body, keys) {
    var out = '---\n';
    keys.forEach(function (k) {
      out += k + ': ' + String(meta[k] == null ? '' : meta[k]).replace(/\s*\n\s*/g, ' ') + '\n';
    });
    return out + '---\n\n' + body.replace(/\s+$/, '') + '\n';
  }

  // ---------- prisijungimas ----------
  function logout(silent) {
    try { localStorage.removeItem(TOKEN_KEY); } catch (e) { }
    token = null;
    renderLogin();
    if (!silent) toast('Atsijungta', 'ok');
  }

  function renderLogin() {
    appEl.innerHTML =
      '<div class="login"><div class="login-card">' +
      '<div class="brand"><div class="brand-ico"><i class="fa-solid fa-microchip"></i></div><div><small>Svetainės valdymas</small><b>REMASTER.LT</b></div></div>' +
      '<h2>Prisijungimas</h2>' +
      '<p>Įklijuokite GitHub raktą (token) su leidimu <b>Contents: Read and write</b> saugyklai <b>remaster</b>. Raktas saugomas tik šiame naršyklės įrenginyje.</p>' +
      '<div class="f"><input type="text" id="tok" placeholder="github_pat_..." autocomplete="off" autocapitalize="off" spellcheck="false"></div>' +
      '<button class="btn" id="go" style="width:100%"><i class="fa-solid fa-right-to-bracket"></i> Prisijungti</button>' +
      '</div></div>';
    var go = document.getElementById('go');
    go.onclick = function () {
      var t = document.getElementById('tok').value.trim();
      if (!t) return toast('Įklijuokite raktą', 'err');
      token = t;
      go.disabled = true;
      api('GET', '').then(function () {
        try { localStorage.setItem(TOKEN_KEY, t); } catch (e) { }
        start();
      }).catch(function (e) {
        token = null; go.disabled = false;
        toast('Nepavyko prisijungti: ' + e.message, 'err');
      });
    };
  }

  // ---------- karkasas ----------
  var NAV = [
    ['straipsniai', 'newspaper', 'Straipsniai'],
    ['supirkimas', 'bag-shopping', 'Supirkimas'],
    ['puslapiai', 'file-lines', 'Puslapiai'],
    '-',
    ['paslaugos', 'screwdriver-wrench', 'Paslaugos'],
    ['kainos', 'tags', 'Kitos kainos'],
    ['nustatymai', 'gear', 'Nustatymai']
  ];

  function renderShell() {
    var nav = NAV.map(function (n) {
      if (n === '-') return '<hr>';
      return '<a href="#/' + n[0] + '" data-v="' + n[0] + '"><i class="fa-regular fa-' + n[1] + '"></i><span>' + n[2] + '</span></a>';
    }).join('');
    appEl.innerHTML =
      '<div class="shell">' +
      '<aside class="side" id="side">' +
      '<div class="brand"><div class="brand-ico"><i class="fa-solid fa-microchip"></i></div><div><small>Kompiuterių taisykla</small><b>REMASTER.LT</b></div></div>' +
      '<nav class="nav">' + nav + '<hr><a href="../index.html" target="_blank" rel="noopener"><i class="fa-solid fa-arrow-up-right-from-square"></i><span>Atidaryti svetainę</span></a></nav>' +
      '<div class="side-foot"><div class="avatar">T</div><div class="who"><b>Valdytojas</b><small>Svetainės redaktorius</small></div>' +
      '<button class="icon-btn" id="logout" title="Atsijungti"><i class="fa-solid fa-right-from-bracket"></i></button></div>' +
      '</aside><div class="scrim" id="scrim"></div>' +
      '<main class="main"><div class="topbar"><button class="icon-btn" id="burger"><i class="fa-solid fa-bars"></i></button><b>Remaster.lt valdymas</b></div><div id="view"></div></main></div>';
    viewEl = document.getElementById('view');
    document.getElementById('logout').onclick = function () { logout(); };
    document.getElementById('burger').onclick = function () { toggleSide(true); };
    document.getElementById('scrim').onclick = function () { toggleSide(false); };
  }
  function toggleSide(open) {
    document.getElementById('side').classList.toggle('open', open);
    document.getElementById('scrim').classList.toggle('open', open);
  }
  function setActive(v) {
    var links = document.querySelectorAll('.nav a[data-v]'), i;
    for (i = 0; i < links.length; i++) links[i].classList.toggle('on', links[i].getAttribute('data-v') === v);
  }

  function route() {
    if (!token || !viewEl) return;
    var h = (location.hash || '#/straipsniai').replace(/^#\/?/, '');
    var parts = h.split('/').map(decodeURIComponent);
    var v = parts[0];
    setActive(v); toggleSide(false); window.scrollTo(0, 0);
    if (COLS[v]) return parts[1] ? editor(v, parts[1]) : listView(v);
    if (v === 'paslaugos') return servicesView();
    if (v === 'kainos') return pricesView();
    if (v === 'nustatymai') return settingsView();
    if (v === 'supirkimas') return buyView();
    location.hash = '#/straipsniai';
  }

  function fail(e) { toast(e.message || 'Įvyko klaida', 'err'); }

  // ---------- sąrašas ----------
  function listView(col) {
    var c = COLS[col];
    viewEl.innerHTML =
      '<h1 class="title">' + c.label + '</h1>' +
      '<div class="sub">' + (col === 'straipsniai' ? 'Straipsniai, rodomi svetainėje.' : 'Papildomi puslapiai (pvz. Apie mus, D.U.K.), nuorodos rodomos svetainės apačioje.') + '</div>' +
      '<div class="bar"><a class="btn" href="#/' + col + '/naujas"><i class="fa-solid fa-plus"></i> Naujas</a></div>' +
      '<div id="lst"></div>';
    var box = document.getElementById('lst');
    loading(box);
    listDir(c.dir).then(function (files) {
      files = files.filter(function (f) { return /\.md$/.test(f.name); });
      files.sort(function (a, b) { return a.name < b.name ? 1 : -1; });
      return Promise.all(files.map(function (f) {
        return getFile(f.path).then(function (x) { return { f: f, m: x ? parseMd(x.text).meta : {} }; });
      }));
    }).then(function (items) {
      if (!items.length) {
        box.innerHTML = '<div class="empty">Dar nėra įrašų. Paspauskite „Naujas“.</div>';
        return;
      }
      box.innerHTML = '<div class="list">' + items.map(function (it) {
        var m = it.m, pills = '';
        if (m.kategorija) pills += '<span class="pill ' + catClass(m.kategorija) + '">' + esc(m.kategorija) + '</span>';
        if (String(m.juodrastis).toLowerCase() === 'taip') pills += '<span class="pill draft">Juodraštis</span>';
        return '<div class="row" data-n="' + esc(it.f.name) + '"><div class="t"><b>' + esc(m.pavadinimas || it.f.name) + '</b>' +
          '<small>' + esc(m.data || '') + '</small></div>' + pills + '<i class="fa-solid fa-chevron-right chev"></i></div>';
      }).join('') + '</div>';
      box.querySelectorAll('.row').forEach(function (r) {
        r.onclick = function () { location.hash = '#/' + col + '/' + encodeURIComponent(r.getAttribute('data-n')); };
      });
    }).catch(function (e) { box.innerHTML = ''; fail(e); });
  }

  // ---------- redaktorius ----------
  function wrapSel(ta, before, after, ph) {
    var s = ta.selectionStart, e = ta.selectionEnd, v = ta.value, sel = v.slice(s, e) || ph || '';
    ta.value = v.slice(0, s) + before + sel + after + v.slice(e);
    ta.focus();
    ta.selectionStart = s + before.length; ta.selectionEnd = s + before.length + sel.length;
  }
  function prefixLines(ta, fn) {
    var v = ta.value, s = ta.selectionStart, e = ta.selectionEnd;
    var ls = v.lastIndexOf('\n', s - 1) + 1, le = v.indexOf('\n', e); if (le < 0) le = v.length;
    var lines = v.slice(ls, le).split('\n').map(fn).join('\n');
    ta.value = v.slice(0, ls) + lines + v.slice(le);
    ta.focus(); ta.selectionStart = ls; ta.selectionEnd = ls + lines.length;
  }
  function insertAt(ta, text) {
    var s = ta.selectionStart, v = ta.value;
    ta.value = v.slice(0, s) + text + v.slice(ta.selectionEnd);
    ta.focus(); ta.selectionStart = ta.selectionEnd = s + text.length;
  }

  function editor(col, name) {
    var c = COLS[col], isNew = name === 'naujas';
    loading(viewEl);
    var p = isNew ? Promise.resolve({ meta: { data: today(), kategorija: CATS[0], juodrastis: 'ne' }, body: '' }) :
      getFile(c.dir + '/' + name).then(function (f) {
        if (!f) throw new Error('Failas nerastas');
        return parseMd(f.text);
      });
    p.then(function (doc) { drawEditor(col, isNew ? null : c.dir + '/' + name, doc); }).catch(function (e) {
      fail(e); location.hash = '#/' + col;
    });
  }

  function drawEditor(col, path, doc) {
    var c = COLS[col], m = doc.meta, cover = m.nuotrauka || '', coverData = '';
    var one = path ? 'Redaguoti' : 'Naujas';
    viewEl.innerHTML =
      '<div class="bar"><a class="btn ghost sm" href="#/' + col + '"><i class="fa-solid fa-arrow-left"></i> Atgal</a></div>' +
      '<h1 class="title">' + one + ' ' + (col === 'straipsniai' ? 'straipsnis' : 'puslapis') + '</h1><div class="sub"></div>' +
      '<div class="card">' +
      '<div class="f"><label>Pavadinimas</label><input type="text" id="f-t" value="' + esc(m.pavadinimas || '') + '"></div>' +
      (c.hasDate ? '<div class="grid2"><div class="f"><label>Data</label><input type="date" id="f-d" value="' + esc(m.data || today()) + '"></div>' +
        '<div class="f"><label>Kategorija</label><input type="text" id="f-c" list="cats" value="' + esc(m.kategorija || '') + '"><datalist id="cats">' +
        CATS.map(function (x) { return '<option value="' + esc(x) + '">'; }).join('') + '</datalist></div></div>' : '') +
      '<div class="f"><label>Trumpas aprašymas</label><input type="text" id="f-a" value="' + esc(m.aprasymas || '') + '"><small>Rodomas sąraše ir Google paieškoje.</small></div>' +
      '<div class="f"><label>Viršelio nuotrauka</label><div class="cover" id="cv"></div>' +
      '<input type="file" id="f-img" accept="image/*" class="hidden"></div>' +
      '<div class="f"><label>Tekstas</label>' +
      '<div class="toolbar" id="tb">' +
      '<button data-a="b" title="Paryškinti"><i class="fa-solid fa-bold"></i></button>' +
      '<button data-a="i" title="Kursyvas"><i class="fa-solid fa-italic"></i></button>' +
      '<button data-a="h2" title="Antraštė">H2</button>' +
      '<button data-a="h3" title="Mažesnė antraštė">H3</button>' +
      '<button data-a="ul" title="Sąrašas"><i class="fa-solid fa-list-ul"></i></button>' +
      '<button data-a="ol" title="Numeruotas sąrašas"><i class="fa-solid fa-list-ol"></i></button>' +
      '<button data-a="q" title="Citata"><i class="fa-solid fa-quote-right"></i></button>' +
      '<button data-a="link" title="Nuoroda"><i class="fa-solid fa-link"></i></button>' +
      '<button data-a="img" title="Įterpti nuotrauką"><i class="fa-regular fa-image"></i></button>' +
      '</div><textarea id="f-b" class="big"></textarea>' +
      '<input type="file" id="f-img2" accept="image/*" class="hidden"></div>' +
      '<div class="f"><label class="chk"><input type="checkbox" id="f-dr"' + (String(m.juodrastis).toLowerCase() === 'taip' ? ' checked' : '') + '> Juodraštis (nerodyti svetainėje)</label></div>' +
      '<div class="actions"><button class="btn" id="save"><i class="fa-solid fa-cloud-arrow-up"></i> Išsaugoti</button>' +
      '<a class="btn ghost" href="#/' + col + '">Atšaukti</a><span class="grow"></span>' +
      (path ? '<button class="btn danger" id="del"><i class="fa-regular fa-trash-can"></i> Ištrinti</button>' : '') + '</div></div>';

    var body = document.getElementById('f-b');
    body.value = doc.body || '';

    function drawCover() {
      var cv = document.getElementById('cv');
      var src = coverData || (cover ? '../nuotraukos/' + encodeURIComponent(cover) : '');
      cv.innerHTML = (src ? '<img src="' + src + '" alt="">' : '<div class="ph">Nėra nuotraukos</div>') +
        '<div style="display:flex;gap:8px;flex-wrap:wrap"><button class="btn ghost sm" id="pick"><i class="fa-regular fa-image"></i> ' + (cover ? 'Pakeisti' : 'Pasirinkti') + '</button>' +
        (cover ? '<button class="btn danger sm" id="unpick">Pašalinti</button>' : '') + '</div>';
      document.getElementById('pick').onclick = function () { document.getElementById('f-img').click(); };
      var un = document.getElementById('unpick');
      if (un) un.onclick = function () { cover = ''; coverData = ''; drawCover(); };
    }
    drawCover();

    document.getElementById('f-img').onchange = function (e) {
      var file = e.target.files[0]; if (!file) return;
      toast('Keliama nuotrauka...');
      uploadImage(file).then(function (r) { cover = r.name; coverData = r.dataUrl; drawCover(); toast('Nuotrauka įkelta', 'ok'); }).catch(fail);
      e.target.value = '';
    };
    document.getElementById('f-img2').onchange = function (e) {
      var file = e.target.files[0]; if (!file) return;
      toast('Keliama nuotrauka...');
      uploadImage(file).then(function (r) {
        insertAt(body, '\n\n![](' + r.name + ')\n\n');
        toast('Nuotrauka įterpta į tekstą', 'ok');
      }).catch(fail);
      e.target.value = '';
    };
    document.getElementById('tb').onclick = function (e) {
      var b = e.target.closest('button'); if (!b) return;
      var a = b.getAttribute('data-a');
      if (a === 'b') wrapSel(body, '**', '**', 'paryškinta');
      else if (a === 'i') wrapSel(body, '*', '*', 'kursyvas');
      else if (a === 'h2') prefixLines(body, function (l) { return '## ' + l.replace(/^#+\s*/, ''); });
      else if (a === 'h3') prefixLines(body, function (l) { return '### ' + l.replace(/^#+\s*/, ''); });
      else if (a === 'ul') prefixLines(body, function (l) { return '- ' + l.replace(/^(-|\d+\.)\s+/, ''); });
      else if (a === 'ol') { var n = 0; prefixLines(body, function (l) { n++; return n + '. ' + l.replace(/^(-|\d+\.)\s+/, ''); }); }
      else if (a === 'q') prefixLines(body, function (l) { return '> ' + l.replace(/^>\s*/, ''); });
      else if (a === 'link') {
        var u = prompt('Nuoroda (https://...)');
        if (u) wrapSel(body, '[', '](' + u + ')', 'nuorodos tekstas');
      } else if (a === 'img') document.getElementById('f-img2').click();
    };

    var del = document.getElementById('del');
    if (del) del.onclick = function () {
      if (!confirm('Tikrai ištrinti? Šio veiksmo atšaukti negalima.')) return;
      del.disabled = true;
      deleteFile(path, 'Ištrinta: ' + (m.pavadinimas || path)).then(function () {
        toast('Ištrinta. Svetainė atsinaujins per ~1 min.', 'ok'); location.hash = '#/' + col;
      }).catch(function (e) { del.disabled = false; fail(e); });
    };

    document.getElementById('save').onclick = function () {
      var btn = this, title = document.getElementById('f-t').value.trim();
      if (!title) return toast('Įveskite pavadinimą', 'err');
      var meta = {
        pavadinimas: title,
        data: c.hasDate ? document.getElementById('f-d').value || today() : '',
        kategorija: c.hasCat ? document.getElementById('f-c').value.trim() : '',
        aprasymas: document.getElementById('f-a').value.trim(),
        nuotrauka: cover,
        juodrastis: document.getElementById('f-dr').checked ? 'taip' : 'ne'
      };
      var keys = c.hasDate ? ['pavadinimas', 'data', 'kategorija', 'aprasymas', 'nuotrauka', 'juodrastis'] :
        ['pavadinimas', 'aprasymas', 'nuotrauka', 'juodrastis'];
      var target = path || (c.dir + '/' + (c.hasDate ? meta.data + '-' : '') + slugify(title) + '.md');
      btn.disabled = true; btn.innerHTML = '<span class="spin"></span>Saugoma...';
      saveText(target, buildMd(meta, body.value, keys), (path ? 'Atnaujinta: ' : 'Pridėta: ') + title).then(function () {
        toast('Išsaugota. Svetainė atsinaujins per ~1 min.', 'ok');
        location.hash = '#/' + col;
      }).catch(function (e) { btn.disabled = false; btn.innerHTML = '<i class="fa-solid fa-cloud-arrow-up"></i> Išsaugoti'; fail(e); });
    };
  }

  // ---------- sąrašų redaktorius (paslaugos, kainos) ----------
  function listEditor(cfg) {
    loading(viewEl);
    loadJson(cfg.file, cfg.def).then(function (items) {
      if (!Array.isArray(items)) items = cfg.def;
      draw();
      function draw() {
        viewEl.innerHTML =
          '<h1 class="title">' + cfg.title + '</h1><div class="sub">' + cfg.sub + '</div>' +
          (cfg.hint ? '<div class="hint">' + cfg.hint + '</div>' : '') +
          '<div id="items">' + items.map(function (it, i) {
            return '<div class="item" data-i="' + i + '"><div class="head"><b>' + cfg.one + ' ' + (i + 1) + '</b>' +
              '<button class="icon-btn" data-act="up" title="Aukštyn"><i class="fa-solid fa-arrow-up"></i></button>' +
              '<button class="icon-btn" data-act="down" title="Žemyn"><i class="fa-solid fa-arrow-down"></i></button>' +
              '<button class="icon-btn" data-act="rm" title="Šalinti" style="color:#ff7a7f"><i class="fa-regular fa-trash-can"></i></button></div>' +
              cfg.fields.map(function (fd) {
                var v = it[fd.k] || '';
                if (fd.t === 'icon') {
                  return '<div class="f"><label>' + fd.l + '</label><div class="iconpick">' + ICONS.map(function (ic) {
                    return '<button type="button" data-ic="' + ic + '" class="' + (v === ic ? 'on' : '') + '"><i class="fa-solid fa-' + ic + '"></i></button>';
                  }).join('') + '</div></div>';
                }
                if (fd.t === 'area') return '<div class="f"><label>' + fd.l + '</label><textarea data-k="' + fd.k + '" style="min-height:90px">' + esc(v) + '</textarea></div>';
                return '<div class="f"><label>' + fd.l + '</label><input type="text" data-k="' + fd.k + '" value="' + esc(v) + '"' + (fd.ph ? ' placeholder="' + esc(fd.ph) + '"' : '') + '></div>';
              }).join('') + '</div>';
          }).join('') + '</div>' +
          '<div class="actions"><button class="btn ghost" id="add"><i class="fa-solid fa-plus"></i> Pridėti</button>' +
          '<button class="btn" id="save"><i class="fa-solid fa-cloud-arrow-up"></i> Išsaugoti</button></div>';

        var box = document.getElementById('items');
        box.oninput = function (e) {
          var k = e.target.getAttribute('data-k'); if (!k) return;
          items[+e.target.closest('.item').getAttribute('data-i')][k] = e.target.value;
        };
        box.onclick = function (e) {
          var el = e.target.closest('.item'); if (!el) return;
          var i = +el.getAttribute('data-i');
          var ic = e.target.closest('[data-ic]');
          if (ic) { items[i].ikona = ic.getAttribute('data-ic'); return draw(); }
          var b = e.target.closest('[data-act]'); if (!b) return;
          var act = b.getAttribute('data-act');
          if (act === 'rm') { if (!confirm('Pašalinti šį įrašą?')) return; items.splice(i, 1); }
          else if (act === 'up' && i > 0) { var t = items[i]; items[i] = items[i - 1]; items[i - 1] = t; }
          else if (act === 'down' && i < items.length - 1) { var t2 = items[i]; items[i] = items[i + 1]; items[i + 1] = t2; }
          draw();
        };
        document.getElementById('add').onclick = function () { items.push(cfg.blank()); draw(); };
        document.getElementById('save').onclick = function () {
          var btn = this;
          var clean = items.filter(function (it) { return (it.pavadinimas || '').trim(); });
          btn.disabled = true; btn.innerHTML = '<span class="spin"></span>Saugoma...';
          saveText(cfg.file, JSON.stringify(clean, null, 2) + '\n', cfg.msg).then(function () {
            items = clean;
            toast('Išsaugota. Svetainė atsinaujins per ~1 min.', 'ok'); draw();
          }).catch(function (e) { btn.disabled = false; btn.innerHTML = '<i class="fa-solid fa-cloud-arrow-up"></i> Išsaugoti'; fail(e); });
        };
      }
    }).catch(function (e) { viewEl.innerHTML = ''; fail(e); });
  }

  function servicesView() {
    listEditor({
      file: 'duomenys/paslaugos.json', msg: 'Atnaujintos paslaugos',
      title: 'Paslaugos', sub: 'Paslaugų kortelės pagrindiniame puslapyje.', one: 'Paslauga',
      hint: 'Jei užpildysite „Kainą“, ji automatiškai atsiras paslaugos kortelėje ir kainų lentelėje, o rašyti jos dar kartą skiltyje „Kainos“ nereikia.',
      def: [], blank: function () { return { ikona: 'screwdriver-wrench', pavadinimas: '', aprasymas: '', kaina: '', kainos_pastaba: '' }; },
      fields: [{ k: 'ikona', t: 'icon', l: 'Piktograma' }, { k: 'pavadinimas', t: 'text', l: 'Pavadinimas' }, { k: 'aprasymas', t: 'area', l: 'Aprašymas' },
        { k: 'kaina', t: 'text', l: 'Kaina (nebūtina)', ph: 'nuo 30 €' }, { k: 'kainos_pastaba', t: 'text', l: 'Kainos pastaba (nebūtina)', ph: 'pvz. kaina su darbu' }]
    });
  }
  function pricesView() {
    listEditor({
      file: 'duomenys/kainos.json', msg: 'Atnaujintos kainos',
      title: 'Kitos kainos', sub: 'Papildomos kainos, kurių nėra tarp paslaugų. Kainos, įrašytos prie paslaugų, į lentelę patenka automatiškai.', one: 'Kaina',
      hint: 'Kainas rašykite taip, kaip norite rodyti, pvz. „nuo 25 €“ arba „30–50 €“.',
      def: [], blank: function () { return { pavadinimas: '', kaina: '', pastaba: '' }; },
      fields: [{ k: 'pavadinimas', t: 'text', l: 'Paslauga' }, { k: 'kaina', t: 'text', l: 'Kaina', ph: 'nuo 25 €' }, { k: 'pastaba', t: 'text', l: 'Pastaba (nebūtina)' }]
    });
  }

  function settingsView() {
    loading(viewEl);
    var def = { email: 'info@remaster.lt', phone: '', city: 'Vilnius, Lietuva', url: '', forma_url: '' };
    loadJson('duomenys/nustatymai.json', def).then(function (s) {
      s = Object.assign({}, def, s);
      viewEl.innerHTML =
        '<h1 class="title">Nustatymai</h1><div class="sub">Kontaktai, rodomi svetainėje.</div>' +
        '<div class="card">' +
        '<div class="f"><label>El. paštas</label><input type="text" id="s-email" value="' + esc(s.email) + '"></div>' +
        '<div class="f"><label>Telefonas</label><input type="text" id="s-phone" value="' + esc(s.phone) + '" placeholder="+370 600 00000"><small>Palikite tuščią, jei nenorite rodyti telefono.</small></div>' +
        '<div class="f"><label>Vieta</label><input type="text" id="s-city" value="' + esc(s.city) + '"></div>' +
        '<div class="f"><label>Svetainės adresas (nebūtina)</label><input type="text" id="s-url" value="' + esc(s.url) + '" placeholder="https://remaster.lt"><small>Naudojamas Google žemėlapiui (sitemap.xml).</small></div>' +
        '<div class="f"><label>Supirkimo užklausų adresas (Google Apps Script)</label><input type="text" id="s-forma" value="' + esc(s.forma_url) + '" placeholder="https://script.google.com/macros/s/.../exec"><small>Kai įrašysite, svetainės supirkimo forma siųs užklausas į jūsų lentelę, o jas matysite skiltyje „Supirkimas“.</small></div>' +
        '<div class="actions"><button class="btn" id="save"><i class="fa-solid fa-cloud-arrow-up"></i> Išsaugoti</button></div></div>';
      document.getElementById('save').onclick = function () {
        var btn = this;
        var out = {
          email: document.getElementById('s-email').value.trim(),
          phone: document.getElementById('s-phone').value.trim(),
          city: document.getElementById('s-city').value.trim(),
          url: document.getElementById('s-url').value.trim(),
          forma_url: document.getElementById('s-forma').value.trim()
        };
        btn.disabled = true; btn.innerHTML = '<span class="spin"></span>Saugoma...';
        saveText('duomenys/nustatymai.json', JSON.stringify(out, null, 2) + '\n', 'Atnaujinti nustatymai').then(function () {
          btn.disabled = false; btn.innerHTML = '<i class="fa-solid fa-cloud-arrow-up"></i> Išsaugoti';
          toast('Išsaugota. Svetainė atsinaujins per ~1 min.', 'ok');
        }).catch(function (e) { btn.disabled = false; btn.innerHTML = '<i class="fa-solid fa-cloud-arrow-up"></i> Išsaugoti'; fail(e); });
      };
    }).catch(function (e) { viewEl.innerHTML = ''; fail(e); });
  }

  // ---------- supirkimo užklausos ----------
  var BUY_KEY = 'rm_buy_key';
  function buyCall(url, params) {
    var q = Object.keys(params).map(function (k) { return k + '=' + encodeURIComponent(params[k]); }).join('&');
    return fetch(url + (url.indexOf('?') > -1 ? '&' : '?') + q + '&_=' + Date.now()).then(function (r) { return r.json(); });
  }
  function contactLinks(k) {
    var v = String(k || '').trim();
    if (v.indexOf('@') > -1) return '<a class="btn sm" href="mailto:' + esc(v) + '"><i class="fa-solid fa-envelope"></i> Rašyti</a>';
    var tel = v.replace(/[^\d+]/g, '');
    return tel ? '<a class="btn sm" href="tel:' + esc(tel) + '"><i class="fa-solid fa-phone"></i> Skambinti</a>' : '';
  }
  function buyView() {
    loading(viewEl);
    loadJson('duomenys/nustatymai.json', {}).then(function (s) {
      var url = (s && s.forma_url) || '';
      var key = ''; try { key = localStorage.getItem(BUY_KEY) || ''; } catch (e) { }
      var head = '<h1 class="title">Supirkimas</h1><div class="sub">Svetainėje pateiktos įrangos supirkimo užklausos.</div>';
      if (!url) {
        viewEl.innerHTML = head + '<div class="card"><div class="hint">Užklausų priėmimas dar nesukonfigūruotas. Reikia vieną kartą nustatyti nemokamą „Google“ lentelę su Apps Script. Kai turėsite jos adresą, įrašykite jį skiltyje <a href="#/nustatymai" style="text-decoration:underline">Nustatymai</a>.</div>' +
          '<p style="color:#c3c3cc">Kol to nepadaryta, svetainės forma atidaro el. pašto programą su paruoštu laišku.</p></div>';
        return;
      }
      if (!key) {
        viewEl.innerHTML = head + '<div class="card"><div class="f"><label>Slaptas raktas</label><input type="text" id="bk" autocomplete="off" autocapitalize="off" placeholder="raktas iš Apps Script kodo (KEY)"><small>Įrašomas tik šiame įrenginyje.</small></div>' +
          '<div class="actions"><button class="btn" id="bk-ok">Tęsti</button></div></div>';
        document.getElementById('bk-ok').onclick = function () {
          var v = document.getElementById('bk').value.trim(); if (!v) return;
          try { localStorage.setItem(BUY_KEY, v); } catch (e) { }
          buyView();
        };
        return;
      }
      viewEl.innerHTML = head + '<div class="bar"><button class="btn ghost sm" id="rf"><i class="fa-solid fa-rotate"></i> Atnaujinti</button><span class="grow"></span><button class="btn ghost sm" id="bk-reset">Pakeisti raktą</button></div><div id="reqs"></div>';
      var box = document.getElementById('reqs');
      document.getElementById('rf').onclick = buyView;
      document.getElementById('bk-reset').onclick = function () { try { localStorage.removeItem(BUY_KEY); } catch (e) { } buyView(); };
      loading(box);
      buyCall(url, { key: key }).then(function (r) {
        if (!r.ok) {
          box.innerHTML = '<div class="empty">' + (r.error === 'key' ? 'Neteisingas raktas. Spauskite „Pakeisti raktą“.' : 'Klaida gaunant duomenis.') + '</div>';
          return;
        }
        if (!r.items.length) { box.innerHTML = '<div class="empty">Užklausų kol kas nėra.</div>'; return; }
        box.innerHTML = r.items.map(function (it) {
          var done = it.busena !== 'Naujas';
          return '<div class="req" data-id="' + esc(it.id) + '"><div class="top"><span class="pill ' + (done ? 'draft' : 'c0') + '">' + esc(it.busena || 'Naujas') + '</span><small>' + esc(it.laikas) + '</small></div>' +
            '<div class="desc">' + esc(it.irenginys) + '</div>' +
            '<div class="contact"><span class="who">' + esc(it.kontaktas) + '</span>' + contactLinks(it.kontaktas) +
            '<button class="btn ghost sm" data-a="st" data-v="' + (done ? 'Naujas' : 'Perziureta') + '">' + (done ? 'Grąžinti į naujas' : 'Pažymėti peržiūrėta') + '</button>' +
            '<button class="btn danger sm" data-a="del"><i class="fa-regular fa-trash-can"></i></button></div></div>';
        }).join('');
        box.onclick = function (e) {
          var b = e.target.closest('button[data-a]'); if (!b) return;
          var id = b.closest('.req').getAttribute('data-id'), a = b.getAttribute('data-a');
          if (a === 'del' && !confirm('Ištrinti šią užklausą?')) return;
          b.disabled = true;
          buyCall(url, a === 'del' ? { key: key, action: 'delete', id: id } : { key: key, action: 'status', id: id, value: b.getAttribute('data-v') })
            .then(function (r2) { if (!r2.ok) throw new Error('Nepavyko'); buyView(); }).catch(fail);
        };
      }).catch(function () { box.innerHTML = '<div class="empty">Nepavyko pasiekti Apps Script adreso. Patikrinkite jį skiltyje Nustatymai.</div>'; });
    }).catch(fail);
  }

  // ---------- paleidimas ----------
  function start() {
    if (!token) return renderLogin();
    renderShell();
    route();
  }
  window.addEventListener('hashchange', route);
  start();
})();
