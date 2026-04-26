/* ------------------------------------------------------------------
 * Deeeeep Research Viewer
 * 加载 manifest 与报告 · 渲染 markdown · 处理引用与 hedging · TOC · 主题
 * ------------------------------------------------------------------ */

(function () {
  'use strict';

  // ---------- 主题 ----------
  const THEME_KEY = 'deeeeep-theme';
  function initTheme() {
    // URL 上的 ?theme=light/dark 优先（也写回 localStorage 持久化）
    const themeParam = new URLSearchParams(location.search).get('theme');
    if (themeParam === 'light' || themeParam === 'dark') {
      localStorage.setItem(THEME_KEY, themeParam);
    }
    const stored = localStorage.getItem(THEME_KEY);
    if (stored === 'dark' || stored === 'light') {
      document.documentElement.setAttribute('data-theme', stored);
    } else {
      const dark = matchMedia('(prefers-color-scheme: dark)').matches;
      document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light');
    }
  }
  function toggleTheme() {
    const cur = document.documentElement.getAttribute('data-theme');
    const next = cur === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem(THEME_KEY, next);
  }
  initTheme();

  // ---------- markdown-it 配置 ----------
  const md = window.markdownit({
    html: false,
    breaks: false,
    linkify: true,
    typographer: false,
  });

  // 标题加 id 但不显示 permalink 符号
  if (window.markdownItAnchor) {
    const anchor = window.markdownItAnchor.default || window.markdownItAnchor;
    md.use(anchor, {
      slugify: slugify,
      tabIndex: false,
    });
  }

  function slugify(s) {
    return 'h-' + s
      .toString()
      .trim()
      .toLowerCase()
      .replace(/[\s　]+/g, '-')
      .replace(/[^\w\-一-龥]/g, '');
  }

  // ---------- 语义映射 ----------
  const HEDGING_ZH = {
    confident:          '证据充分',
    probably:           '倾向支持',
    may:                '存在可能',
    evidence_uncertain: '证据不足',
    appears_to:         '未经核实',
    suggests:           '方向性结论',
    cannot_determine:   '无法裁决',
  };

  const TIER_ZH = {
    T1: '权威来源',
    T2: '可靠来源',
    T3: '参考来源',
    T4: '弱来源',
    T5: '不可用',
  };

  // ---------- 工具 ----------
  function escapeHtml(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  function fmtDate(ts) {
    const d = new Date(ts * 1000);
    const Y = d.getFullYear();
    const M = String(d.getMonth() + 1).padStart(2, '0');
    const D = String(d.getDate()).padStart(2, '0');
    return `${Y}-${M}-${D}`;
  }

  function fmtWords(n) {
    if (n == null) return '';
    if (n < 1000) return n + ' 字';
    if (n < 10000) return (n / 1000).toFixed(1).replace(/\.0$/, '') + 'k 字';
    return Math.round(n / 1000) + 'k 字';
  }

  // ---------- 共享 DOM 引用（提前声明便于后续监听挂载） ----------
  const content = document.getElementById('content');
  const pop = document.getElementById('cite-pop');

  // ---------- 报告库 ----------
  const drawer = document.getElementById('library-drawer');
  const scrim = document.getElementById('library-scrim');
  const libraryList = document.getElementById('library-list');
  const libraryCount = document.getElementById('library-count');
  const librarySearch = document.getElementById('library-search');
  let searchQuery = '';

  function openLibrary() {
    drawer.hidden = false;
    scrim.hidden = false;
    requestAnimationFrame(() => {
      drawer.classList.add('is-open');
      scrim.classList.add('is-open');
      // 打开时聚焦搜索框
      setTimeout(() => librarySearch && librarySearch.focus(), 240);
    });
  }
  function closeLibrary() {
    drawer.classList.remove('is-open');
    scrim.classList.remove('is-open');
    setTimeout(() => { drawer.hidden = true; scrim.hidden = true; }, 240);
  }

  document.getElementById('library-btn').addEventListener('click', openLibrary);
  document.getElementById('library-close').addEventListener('click', closeLibrary);
  scrim.addEventListener('click', closeLibrary);
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') closeLibrary();
  });

  function getFilteredReports() {
    const all = (manifestData && manifestData.reports) || [];
    const q = searchQuery.trim().toLowerCase();
    if (!q) return all;
    return all.filter(r => (r.title || '').toLowerCase().includes(q));
  }

  function renderLibrary() {
    const all = (manifestData && manifestData.reports) || [];
    const reports = getFilteredReports();
    libraryCount.textContent = all.length;
    libraryList.innerHTML = '';

    if (all.length === 0) {
      libraryList.innerHTML = '<div class="empty"><p>reports/ 目录里还没有 .md 报告。</p></div>';
      return;
    }
    if (reports.length === 0) {
      libraryList.innerHTML = `<div class="empty"><p>没有匹配 "${escapeHtml(searchQuery)}" 的报告。</p></div>`;
      return;
    }

    reports.forEach(r => {
      const card = document.createElement('button');
      card.className = 'lib-card';
      card.dataset.name = r.name;
      if (r.name === currentReportName) card.classList.add('is-current');

      const meta = [
        fmtDate(r.mtime),
        fmtWords(r.word_count),
      ].filter(Boolean).join('<span style="opacity:.5"> · </span>');

      card.innerHTML = `
        <div class="lib-card__title">${escapeHtml(r.title)}</div>
        <div class="lib-card__meta">${meta}</div>
      `;
      card.addEventListener('click', () => {
        loadReport(r.name);
        closeLibrary();
      });
      libraryList.appendChild(card);
    });
  }

  if (librarySearch) {
    librarySearch.addEventListener('input', e => {
      searchQuery = e.target.value;
      renderLibrary();
    });
  }

  // ---------- 路由 ----------
  function getRouteReport() {
    const params = new URLSearchParams(location.search);
    return params.get('report');
  }
  function setRoute(name) {
    const url = new URL(location.href);
    url.searchParams.set('report', name);
    url.hash = '';
    history.replaceState(null, '', url.toString());
  }

  // ---------- 加载报告 ----------
  let manifestData = null;
  let currentReportName = null;
  let currentSources = [];

  async function loadManifest() {
    const r = await fetch('manifest.json', { cache: 'no-store' });
    if (!r.ok) throw new Error('manifest 加载失败 ' + r.status);
    manifestData = await r.json();
    return manifestData;
  }

  async function loadReport(name) {
    const meta = manifestData.reports.find(r => r.name === name);
    if (!meta) {
      document.getElementById('content').innerHTML =
        `<div class="empty"><p>找不到报告 "${escapeHtml(name)}"。</p></div>`;
      return;
    }
    currentReportName = name;

    // 切换前清理上一份报告残留
    pop.classList.remove('is-open');
    pop.hidden = true;
    if (scrollObserver) { content.removeEventListener('scroll', scrollObserver); scrollObserver = null; }
    document.getElementById('toc-list').innerHTML = '';

    setRoute(name);
    document.title = meta.title + ' · Deeeeep Research';

    // sources 优先加载（如果有的话）
    currentSources = [];
    if (meta.has_sources && meta.sources_file) {
      try {
        const sr = await fetch('../' + meta.sources_file, { cache: 'no-store' });
        if (sr.ok) {
          const sj = await sr.json();
          currentSources = Array.isArray(sj) ? sj : (sj.sources || []);
        }
      } catch (e) { console.warn('sources 加载失败', e); }
    }

    // markdown
    const mr = await fetch('../' + meta.file, { cache: 'no-store' });
    if (!mr.ok) {
      document.getElementById('content').innerHTML =
        `<div class="empty"><p>报告文件加载失败。</p></div>`;
      return;
    }
    const text = await mr.text();
    const html = md.render(text);
    const article = document.createElement('article');
    article.className = 'report';
    article.innerHTML = html;

    tagReferenceItems(article);
    processInlineMarkers(article);
    applyCiteTiers(article);
    renderReferencesSection(article);

    content.innerHTML = '';
    content.appendChild(article);

    buildTOC(article);

    // 重新渲染 library 高亮
    renderLibrary();

    // 切换报告始终回顶部
    content.scrollTop = 0;
  }

  // ---------- 内联标记替换 ----------
  // [hedging:xxx]  →  <span class="hedging hedging-xxx">xxx</span>
  // [N]            →  <a class="cite" data-num="N" href="#ref-N">N</a>
  const MARKER_RE = /\[hedging:([a-z_]+)\]|\[(\d+)\]/g;

  function processInlineMarkers(root) {
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode(node) {
        const p = node.parentElement;
        if (!p) return NodeFilter.FILTER_REJECT;
        if (p.closest('code, pre, a.heading-anchor, .cite, .hedging')) {
          return NodeFilter.FILTER_REJECT;
        }
        return MARKER_RE.test(node.nodeValue)
          ? NodeFilter.FILTER_ACCEPT
          : NodeFilter.FILTER_REJECT;
      },
    });
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);

    for (const node of nodes) {
      const text = node.nodeValue;
      const frag = document.createDocumentFragment();
      let last = 0;
      let m;
      MARKER_RE.lastIndex = 0;
      while ((m = MARKER_RE.exec(text)) !== null) {
        if (m.index > last) {
          frag.appendChild(document.createTextNode(text.slice(last, m.index)));
        }
        if (m[1]) {
          const span = document.createElement('span');
          const cls = (m[1] || '').replace(/_/g, '-');
          span.className = 'hedging hedging-' + cls;
          span.textContent = HEDGING_ZH[m[1]] || m[1].replace(/_/g, ' ');
          frag.appendChild(span);
        } else if (m[2]) {
          const a = document.createElement('a');
          a.className = 'cite';
          a.dataset.num = m[2];
          a.href = '#ref-' + m[2];
          a.textContent = m[2];
          frag.appendChild(a);
        }
        last = MARKER_RE.lastIndex;
      }
      if (last < text.length) {
        frag.appendChild(document.createTextNode(text.slice(last)));
      }
      node.parentNode.replaceChild(frag, node);
    }
  }

  // 给所有以 [N] 开头的 LI / P 加 id="ref-N"，便于 cite 链接跳转。
  // 必须先于 processInlineMarkers 跑，否则 [N] 已被替换成 chip 就匹配不到了。
  function tagReferenceItems(root) {
    const candidates = root.querySelectorAll('li, p');
    candidates.forEach(el => {
      const t = el.textContent.trim();
      const m = t.match(/^\[(\d+)\]/);
      if (m && !el.id) el.id = 'ref-' + m[1];
    });
  }

  // ---------- 角标按来源档位着色 ----------
  function applyCiteTiers(root) {
    if (currentSources.length === 0) return;
    const tierMap = {};
    currentSources.forEach(s => { tierMap[s.num] = (s.authority_tier || '').toLowerCase(); });
    root.querySelectorAll('.cite').forEach(cite => {
      const num = parseInt(cite.dataset.num, 10);
      const tier = tierMap[num];
      if (tier) cite.classList.add('cite-' + tier);
    });
  }

  // ---------- 底部引用来源列表 ----------
  function renderReferencesSection(article) {
    if (currentSources.length === 0) return;

    // markdown 自带的 `## 引用来源` 段是 raw md 自洽的硬性要求（phase4 文档「文档骨架」第 6 条）。
    // viewer 模式下要把它移除，再用 sources.json 的富展示版本（带 tier 标签、原文摘录）替代。
    // 移除范围：H2「引用来源」+ 它后面到下一个 H2 之前的所有元素。
    const allH2 = article.querySelectorAll('h2');
    for (const h2 of allH2) {
      if (h2.textContent.trim() === '引用来源') {
        let node = h2.nextElementSibling;
        while (node && node.tagName !== 'H2') {
          const next = node.nextElementSibling;
          node.remove();
          node = next;
        }
        h2.remove();
        break;
      }
    }

    const section = document.createElement('section');
    section.className = 'references-section';

    const heading = document.createElement('h2');
    heading.id = slugify('引用来源');
    heading.textContent = '引用来源';
    section.appendChild(heading);

    const list = document.createElement('ol');
    list.className = 'references-list';

    const sorted = [...currentSources].sort((a, b) => a.num - b.num);
    sorted.forEach(src => {
      const li = document.createElement('li');
      li.id = 'ref-' + src.num;
      li.className = 'ref-item';
      li.dataset.num = String(src.num);

      const tier = src.authority_tier || '';
      const tierLabel = TIER_ZH[tier] || tier;
      const tierHtml = tier
        ? `<span class="ref-tier t-${escapeHtml(tier)}">${escapeHtml(tierLabel)}</span>`
        : '';
      const dateHtml = src.date
        ? `<span class="ref-date">${escapeHtml(src.date)}</span>`
        : '';

      li.innerHTML = `
        <div class="ref-head">
          <span class="ref-num">[${src.num}]</span>
          ${tierHtml}
          ${dateHtml}
        </div>
        ${src.title ? `<div class="ref-title">${escapeHtml(src.title)}</div>` : ''}
        ${src.evidence_quote ? `<div class="ref-quote">${escapeHtml(src.evidence_quote)}</div>` : ''}
        ${src.url ? `<a class="ref-url" href="${escapeHtml(src.url)}" target="_blank" rel="noopener">${escapeHtml(src.url)}</a>` : ''}
      `;
      list.appendChild(li);
    });

    section.appendChild(list);
    article.appendChild(section);
  }

  // ---------- TOC ----------
  let scrollObserver = null;
  function buildTOC(root) {
    const list = document.getElementById('toc-list');
    list.innerHTML = '';
    const headings = root.querySelectorAll('h2, h3, h4');
    if (headings.length === 0) {
      list.innerHTML = '<li style="color:var(--ink-mute);font-size:0.82rem;padding-left:6px">（无章节）</li>';
      return;
    }
    const links = new Map();
    let clickLock = false;
    headings.forEach(h => {
      const id = h.id;
      if (!id) return;
      const level = parseInt(h.tagName[1], 10);
      const text = h.textContent.replace(/[¶§#]/g, '').trim();
      const li = document.createElement('li');
      const a = document.createElement('a');
      a.textContent = text;
      a.className = 'lvl-' + level;
      a.dataset.tocId = id;
      a.role = 'link';
      a.addEventListener('click', e => {
        const target = document.getElementById(id);
        if (target) {
          // 点击后锁定 observer 600ms，防止滚动途中切换高亮
          clickLock = true;
          setTimeout(() => { clickLock = false; }, 600);
          // 先手动设置高亮
          links.forEach(l => l.classList.remove('is-active'));
          a.classList.add('is-active');
          lastActiveId = id;
          history.replaceState(null, '', '#' + id);
          target.scrollIntoView({ behavior: 'auto', block: 'start' });
        }
      });
      li.appendChild(a);
      list.appendChild(li);
      links.set(id, a);
    });

    // ScrollSpy：scroll 事件 + 最后一个滚过顶部的标题
    if (scrollObserver) { content.removeEventListener('scroll', scrollObserver); }
    const headingEls = Array.from(headings).filter(h => h.id);
    let lastActiveId = null;

    function updateActiveHeading() {
      if (clickLock) return;
      const contentTop = content.getBoundingClientRect().top;
      const threshold = contentTop + 90;
      let activeId = null;
      for (const h of headingEls) {
        if (h.getBoundingClientRect().top <= threshold) {
          activeId = h.id;
        }
      }
      if (!activeId && headingEls.length) activeId = headingEls[0].id;
      if (activeId && activeId !== lastActiveId) {
        lastActiveId = activeId;
        links.forEach(l => l.classList.remove('is-active'));
        const link = links.get(activeId);
        if (link) {
          link.classList.add('is-active');
          const tocList = document.getElementById('toc-list');
          const linkRect = link.getBoundingClientRect();
          const listRect = tocList.getBoundingClientRect();
          if (linkRect.top < listRect.top + 20 || linkRect.bottom > listRect.bottom - 20) {
            link.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
          }
        }
      }
    }

    scrollObserver = updateActiveHeading;
    content.addEventListener('scroll', updateActiveHeading, { passive: true });
    updateActiveHeading();
  }

  // ---------- 引用 popover ----------
  let hidePopTimer = null;

  function showCitePopover(cite) {
    clearTimeout(hidePopTimer);
    const num = parseInt(cite.dataset.num, 10);
    const src = currentSources.find(s => s.num === num);
    if (!src) return;
    const tier = src.authority_tier || '';
    const tierLabel = TIER_ZH[tier] || tier;
    pop.innerHTML = `
      <div class="cite-pop__head">
        <span class="cite-pop__num">[${num}]</span>
        ${tier ? `<span class="cite-pop__tier t-${escapeHtml(tier)}">${escapeHtml(tierLabel)}</span>` : ''}
        ${src.date ? `<span class="cite-pop__date">${escapeHtml(src.date)}</span>` : ''}
      </div>
      ${src.title ? `<div class="cite-pop__title">${escapeHtml(src.title)}</div>` : ''}
      ${src.evidence_quote ? `<div class="cite-pop__quote">${escapeHtml(src.evidence_quote)}</div>` : ''}
      ${src.url ? `<a class="cite-pop__url" href="${escapeHtml(src.url)}" target="_blank" rel="noopener">${escapeHtml(src.url)}</a>` : ''}
    `;
    pop.hidden = false;
    requestAnimationFrame(() => {
      pop.classList.add('is-open');
      // popover 用 position: fixed，全部用 viewport 坐标
      const rect = cite.getBoundingClientRect();
      const popRect = pop.getBoundingClientRect();
      const margin = 12;
      let left = rect.left + rect.width / 2 - popRect.width / 2;
      let top = rect.bottom + 8;
      left = Math.max(margin, Math.min(left, window.innerWidth - popRect.width - margin));
      if (top + popRect.height > window.innerHeight - margin) {
        top = rect.top - popRect.height - 8;
      }
      pop.style.left = left + 'px';
      pop.style.top = top + 'px';
    });
  }

  function scheduleHidePopover() {
    clearTimeout(hidePopTimer);
    hidePopTimer = setTimeout(() => {
      pop.classList.remove('is-open');
      setTimeout(() => {
        if (!pop.classList.contains('is-open')) pop.hidden = true;
      }, 80);
    }, 50);
  }

  document.addEventListener('mouseover', e => {
    const cite = e.target.closest('.cite');
    if (cite) showCitePopover(cite);
  });
  document.addEventListener('mouseout', e => {
    const cite = e.target.closest('.cite');
    if (!cite) return;
    if (e.relatedTarget && (e.relatedTarget.closest('.cite-pop') === pop)) return;
    scheduleHidePopover();
  });
  pop.addEventListener('mouseenter', () => clearTimeout(hidePopTimer));
  pop.addEventListener('mouseleave', scheduleHidePopover);

  // 内容区滚动时关闭 popover
  content.addEventListener('scroll', () => {
    if (pop.classList.contains('is-open')) scheduleHidePopover();
  }, { passive: true });

  // 触屏：tap cite 显示
  document.addEventListener('click', e => {
    const cite = e.target.closest('.cite');
    if (cite) {
      e.preventDefault();
      if (pop.classList.contains('is-open')) {
        scheduleHidePopover();
      } else {
        showCitePopover(cite);
      }
    } else if (!e.target.closest('.cite-pop')) {
      scheduleHidePopover();
    }
  });

  // ---------- 专注模式 ----------
  const FOCUS_KEY = 'deeeeep-focus';
  const focusBtn = document.getElementById('focus-toggle');
  let focusGuide = null;

  function initFocus() {
    const stored = localStorage.getItem(FOCUS_KEY);
    if (stored === 'on') document.documentElement.setAttribute('data-focus', '');
  }

  function toggleFocus() {
    const on = document.documentElement.hasAttribute('data-focus');
    if (on) {
      document.documentElement.removeAttribute('data-focus');
      localStorage.setItem(FOCUS_KEY, 'off');
      disableFocusTracking();
    } else {
      document.documentElement.setAttribute('data-focus', '');
      localStorage.setItem(FOCUS_KEY, 'on');
      enableFocusTracking();
    }
  }

  let focusActiveEl = null;
  let focusMouseX = 0, focusMouseY = 0;

  function updateFocusAt(clientX, clientY) {
    const report = content.querySelector('.report');
    if (!report) return;
    const contentRect = content.getBoundingClientRect();
    if (clientY < contentRect.top || clientY > contentRect.bottom) return;
    const probeX = contentRect.left + 100;
    const el = document.elementFromPoint(probeX, clientY);
    if (!el) return;
    const target = el.closest('.report > *');
    if (target === focusActiveEl) return;
    if (focusActiveEl) focusActiveEl.classList.remove('focus-active');
    focusActiveEl = target;
    if (focusActiveEl) focusActiveEl.classList.add('focus-active');
  }

  function onFocusMove(e) {
    focusMouseX = e.clientX;
    focusMouseY = e.clientY;
    updateFocusAt(focusMouseX, focusMouseY);
  }

  function onFocusScroll() {
    if (focusMouseX || focusMouseY) updateFocusAt(focusMouseX, focusMouseY);
  }

  function enableFocusTracking() {
    document.addEventListener('mousemove', onFocusMove, { passive: true });
    content.addEventListener('scroll', onFocusScroll, { passive: true });
  }

  function disableFocusTracking() {
    document.removeEventListener('mousemove', onFocusMove);
    content.removeEventListener('scroll', onFocusScroll);
    if (focusActiveEl) { focusActiveEl.classList.remove('focus-active'); focusActiveEl = null; }
  }

  focusBtn.addEventListener('click', toggleFocus);
  initFocus();
  if (document.documentElement.hasAttribute('data-focus')) enableFocusTracking();

  // ---------- 边缘渐隐 ----------
  function updateFadeClasses(el) {
    const t = el.scrollTop;
    const atTop = t <= 2;
    const atBottom = t + el.clientHeight >= el.scrollHeight - 2;
    el.classList.toggle('fade-top', !atTop);
    el.classList.toggle('fade-bottom', !atBottom);
  }

  function initFade(el) {
    updateFadeClasses(el);
    el.addEventListener('scroll', () => updateFadeClasses(el), { passive: true });
  }

  initFade(content);
  const tocList = document.getElementById('toc-list');
  if (tocList) initFade(tocList);
  const libList = document.getElementById('library-list');
  if (libList) initFade(libList);

  // ---------- 主题切换 ----------
  document.getElementById('theme-toggle').addEventListener('click', toggleTheme);

  // ---------- 启动 ----------
  (async function start() {
    try {
      const initialHash = location.hash;
      await loadManifest();
      renderLibrary();

      // ?open=library 用于调试
      if (new URLSearchParams(location.search).get('open') === 'library') {
        setTimeout(openLibrary, 50);
      }

      const fromRoute = getRouteReport();
      const initial = fromRoute && manifestData.reports.find(r => r.name === fromRoute)
        ? fromRoute
        : (manifestData.reports[0] && manifestData.reports[0].name);

      if (initial) {
        await loadReport(initial);
        // 初次加载时若 URL 带 hash、跳到对应章节
        if (initialHash) {
          const id = decodeURIComponent(initialHash.slice(1));
          const target = document.getElementById(id);
          if (target) {
            history.replaceState(null, '', location.pathname + location.search + initialHash);
            target.scrollIntoView({ block: 'start' });
          }
        }
      } else {
        document.getElementById('content').innerHTML =
          '<div class="empty"><p>reports/ 目录里还没有 .md 报告。</p></div>';
      }

      window.addEventListener('popstate', () => {
        const r = getRouteReport();
        if (r && r !== currentReportName) loadReport(r);
      });
    } catch (e) {
      console.error(e);
      document.getElementById('content').innerHTML =
        `<div class="empty"><p>启动失败：${escapeHtml(e.message)}</p></div>`;
    }
  })();
})();
