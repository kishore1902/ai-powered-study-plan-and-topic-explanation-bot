/* Shared browser helpers: session token, Groq key (kept in this browser only) and the API caller. */
(function () {
  'use strict';
  const T = 'gf:token', U = 'gf:user', K = 'gf:groqkey', M = 'gf:model';

  async function api(path, opt) {
    opt = opt || {};
    const headers = { Authorization: 'Bearer ' + (localStorage.getItem(T) || '') };
    const key = localStorage.getItem(K);
    if (key) headers['X-Groq-Key'] = key;
    headers['X-Groq-Model'] = localStorage.getItem(M) || 'openai/gpt-oss-120b';
    let body;
    if (opt.form) body = opt.form;
    else if (opt.body !== undefined) { headers['Content-Type'] = 'application/json'; body = JSON.stringify(opt.body); }
    let res;
    try { res = await fetch('/api' + path, { method: opt.method || 'GET', headers, body }); }
    catch (e) { throw new Error('Could not reach the server. Is it running?'); }
    let data = {};
    try { data = await res.json(); } catch (e) { /* empty body */ }
    if (res.status === 401 && !opt.noRedirect) { GF.logout(); location.replace('index.html'); throw new Error('Please log in again.'); }
    if (!res.ok) {
      let d = data.detail;
      if (Array.isArray(d)) d = d.map(x => x.msg).join('; ');
      throw new Error(d || res.statusText || 'Request failed');
    }
    return data;
  }

  window.GF = {
    api,
    setSession(s) { localStorage.setItem(T, s.token); localStorage.setItem(U, JSON.stringify(s.user)); },
    user() { try { return JSON.parse(localStorage.getItem(U)); } catch (e) { return null; } },
    loggedIn() { return !!localStorage.getItem(T); },
    logout() { localStorage.removeItem(T); localStorage.removeItem(U); },
    requireLogin() { if (!GF.loggedIn()) { location.replace('index.html'); return false; } return true; },
    redirectIfLoggedIn() { if (GF.loggedIn()) location.replace('app.html'); },
    getKey() { return localStorage.getItem(K) || ''; },
    setKey(k) { if (k && k.trim()) localStorage.setItem(K, k.trim()); else localStorage.removeItem(K); },
    getModel() { return localStorage.getItem(M) || 'openai/gpt-oss-120b'; },
    setModel(m) { localStorage.setItem(M, (m || '').trim() || 'openai/gpt-oss-120b'); }
  };
})();
