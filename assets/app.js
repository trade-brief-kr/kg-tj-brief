(function () {
  'use strict';
  var KG = '키르기스스탄', TJ = '타지키스탄';
  var $ = function (id) { return document.getElementById(id); };
  var state = { latest: null, report: null, index: [], filter: '', cache: {} };
  try { state.filter = localStorage.getItem('kgtj-filter') || ''; } catch (e) { /* ignore */ }

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function safeUrl(u) { return /^https?:\/\//i.test(u || '') ? u : ''; }
  function dotDate(d) { return (d || '').replace(/-/g, '.'); }
  function hm(iso) { var m = /T(\d{2}:\d{2})/.exec(iso || ''); return m ? m[1] : ''; }

  function itemClass(it) {
    var c = it.countries || [];
    var kg = c.indexOf(KG) >= 0, tj = c.indexOf(TJ) >= 0;
    return kg && tj ? 'kgtj-item' : kg ? 'kg-item' : tj ? 'tj-item' : '';
  }
  function matches(it) {
    if (!state.filter) return true;
    var c = it.countries || [];
    return c.indexOf(state.filter === 'kg' ? KG : TJ) >= 0;
  }

  function bulletHtml(b) {
    var h = '<li class="bullet">' + esc(b.text);
    var u = safeUrl(b.url);
    if (u) {
      h += ' <a class="src" href="' + esc(u) + '" target="_blank" rel="noopener">' + esc(b.source || '출처') + '</a>';
      var a = safeUrl(b.altUrl);
      if (a) h += '<a class="src-alt" href="' + esc(a) + '" target="_blank" rel="noopener">재게재</a>';
    }
    return h + '</li>';
  }

  function render() {
    var r = state.report, el = $('brief');
    if (!r) { el.innerHTML = '<p class="muted">보고서를 불러오지 못했습니다.</p>'; return; }
    $('report-date').textContent = '★ 5분 통상 브리핑 (' + dotDate(r.date) + ')';
    $('updated').textContent = '확인시각 ' + hm(r.generatedAt) + ' KST｜' + (r.coverage || '');
    var h = '<section class="card headline"><div class="label">오늘의 핵심</div><p class="big">' + esc(r.headline) + '</p></section>';
    var shown = 0;
    r.sections.forEach(function (s) {
      var items = s.items.filter(matches);
      h += '<section class="card"><h2>' + esc(s.title) + '</h2>';
      if (!items.length) {
        h += '<p class="empty">' + (s.items.length ? '선택한 국가 관련 항목 없음 (전체 ' + s.items.length + '건)' : '확인된 항목 없음') + '</p>';
      }
      items.forEach(function (it) {
        shown++;
        h += '<article class="item ' + itemClass(it) + '">';
        if (it.tag || it.title) h += '<h3><span class="itag">' + esc(it.tag) + '</span>' + esc(it.title) + '</h3>';
        h += '<ul>' + it.bullets.map(bulletHtml).join('') + '</ul></article>';
      });
      h += '</section>';
    });
    if (r.notes && r.notes.length) {
      h += '<div class="notes"><b>참고</b><ul>' + r.notes.map(function (n) { return '<li>· ' + esc(n) + '</li>'; }).join('') + '</ul></div>';
    }
    el.innerHTML = h;
    $('copy').disabled = !shown;
    var isLatest = state.latest && r.date === state.latest.date;
    $('archive-banner').hidden = !!isLatest;
    if (!isLatest) $('archive-banner-text').textContent = dotDate(r.date) + ' 지난 보고서를 보고 있습니다.';
    updateNav();
  }

  function copyText() {
    var r = state.report; if (!r) return '';
    var out = ['★ 5분 통상 브리핑 (' + dotDate(r.date) + ')', '확인시각 ' + hm(r.generatedAt) + ' KST｜' + r.coverage,
      '오늘의 핵심 — ' + r.headline];
    if (state.filter) out.push('(필터: ' + (state.filter === 'kg' ? KG : TJ) + ' 관련 항목만)');
    r.sections.forEach(function (s) {
      var items = s.items.filter(matches);
      if (!items.length) return;
      out.push(s.title);
      items.forEach(function (it) {
        if (it.tag || it.title) out.push((it.tag ? it.tag + ' ' : '') + it.title);
        it.bullets.forEach(function (b) {
          out.push(b.text + (safeUrl(b.url) ? ' [' + (b.source || '출처') + '](' + b.url + ')' : ''));
        });
      });
    });
    return out.join('\n');
  }

  function flash(msg) { $('status').textContent = msg; setTimeout(function () { $('status').textContent = ''; }, 2500); }

  function doCopy() {
    var t = copyText();
    var done = function () { flash('브리핑 텍스트를 복사했습니다.'); };
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(t).then(done, fallback);
    } else fallback();
    function fallback() {
      var ta = document.createElement('textarea'); ta.value = t; document.body.appendChild(ta); ta.select();
      try { document.execCommand('copy'); done(); } catch (e) { flash('복사 실패: 직접 선택해 복사하세요.'); }
      document.body.removeChild(ta);
    }
  }

  function setFilter(f) {
    state.filter = f;
    try { localStorage.setItem('kgtj-filter', f); } catch (e) { /* ignore */ }
    document.body.setAttribute('data-filter', f);
    if (!f) document.body.removeAttribute('data-filter');
    Array.prototype.forEach.call(document.querySelectorAll('.filter button'), function (b) {
      b.setAttribute('aria-pressed', String(b.getAttribute('data-f') === f));
    });
    render();
  }

  function updateNav() {
    var sel = $('archive-date'), idx = state.index;
    if (!idx.length) return;
    sel.innerHTML = idx.map(function (e, i) {
      return '<option value="' + esc(e.date) + '">' + esc(dotDate(e.date)) + (i === 0 ? ' (최신)' : '') + '</option>';
    }).join('');
    sel.disabled = idx.length < 2;
    var cur = state.report ? state.report.date : '';
    sel.value = cur;
    var pos = idx.findIndex(function (e) { return e.date === cur; });
    $('prev-day').disabled = pos < 0 || pos >= idx.length - 1;
    $('next-day').disabled = pos <= 0;
  }

  function loadScript(src) {
    return new Promise(function (ok, fail) {
      var s = document.createElement('script'); s.src = src; s.onload = ok; s.onerror = fail; document.head.appendChild(s);
    });
  }
  function fetchJson(path) {
    return fetch(path, { cache: 'no-cache' }).then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); });
  }
  function loadDate(d) {
    if (state.latest && d === state.latest.date) return Promise.resolve(state.latest);
    if (state.cache[d]) return Promise.resolve(state.cache[d]);
    return fetchJson('data/archive/' + d + '.json').catch(function () {
      return loadScript('data/archive/' + d + '.js').then(function () { return (window.REPORT_ARCHIVE || {})[d]; });
    }).then(function (r) { if (!r) throw new Error('없음'); state.cache[d] = r; return r; });
  }
  function show(d, push) {
    loadDate(d).then(function (r) {
      state.report = r; render();
      if (push) {
        var u = new URL(location.href);
        if (state.latest && d === state.latest.date) u.searchParams.delete('date'); else u.searchParams.set('date', d);
        history.replaceState(null, '', u);
      }
    }).catch(function () { flash(dotDate(d) + ' 보고서를 불러오지 못했습니다.'); });
  }
  function step(delta) {
    var pos = state.index.findIndex(function (e) { return e.date === state.report.date; });
    var next = state.index[pos + delta];
    if (next) show(next.date, true);
  }

  function selectTab(which) {
    var brief = which !== 'profile';
    $('brief-tab').setAttribute('aria-selected', String(brief)); $('profile-tab').setAttribute('aria-selected', String(!brief));
    $('brief-tab').tabIndex = brief ? 0 : -1; $('profile-tab').tabIndex = brief ? -1 : 0;
    $('brief').hidden = !brief; $('profile').hidden = brief;
    document.querySelector('.day-nav').style.visibility = brief ? '' : 'hidden';
    $('copy').hidden = !brief;
    if (brief) { if (location.hash === '#profile') history.replaceState(null, '', location.pathname + location.search); }
    else if (location.hash !== '#profile' && !/^#p-/.test(location.hash)) history.replaceState(null, '', '#profile');
  }

  function init() {
    $('copy').addEventListener('click', doCopy);
    $('prev-day').addEventListener('click', function () { step(1); });
    $('next-day').addEventListener('click', function () { step(-1); });
    $('archive-date').addEventListener('change', function (e) { show(e.target.value, true); });
    $('to-latest').addEventListener('click', function () { if (state.latest) show(state.latest.date, true); });
    $('brief-tab').addEventListener('click', function () { selectTab('brief'); });
    $('profile-tab').addEventListener('click', function () { selectTab('profile'); });
    document.querySelector('nav').addEventListener('keydown', function (e) {
      if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
        var toProfile = $('brief-tab').getAttribute('aria-selected') === 'true';
        selectTab(toProfile ? 'profile' : 'brief'); $(toProfile ? 'profile-tab' : 'brief-tab').focus();
      }
    });
    Array.prototype.forEach.call(document.querySelectorAll('.filter button'), function (b) {
      b.addEventListener('click', function () { setFilter(b.getAttribute('data-f')); });
    });
    Array.prototype.forEach.call(document.querySelectorAll('.toc a'), function (a) {
      a.addEventListener('click', function () { selectTab('profile'); });
    });
    if (location.hash === '#profile' || /^#p-/.test(location.hash)) { selectTab('profile'); if (location.hash === '#profile') setTimeout(function () { window.scrollTo(0, 0); }, 0); }

    var latestP = fetchJson('data/report.json').catch(function () { return window.REPORT_DATA; });
    var indexP = fetchJson('data/archive/index.json').catch(function () { return window.REPORT_INDEX || []; });
    Promise.all([latestP, indexP]).then(function (res) {
      state.latest = res[0]; state.index = res[1] || [];
      if (state.latest && !state.index.some(function (e) { return e.date === state.latest.date; })) state.index.unshift({ date: state.latest.date });
      state.report = state.latest;
      setFilter(state.filter);
      var want = new URL(location.href).searchParams.get('date');
      if (want && state.latest && want !== state.latest.date) show(want, false);
    }).catch(function () { render(); });
  }
  document.addEventListener('DOMContentLoaded', init);
}());
