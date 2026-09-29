/* hermes-pwa — app móvel do Hermes. Vanilla JS, sem build. */
(function () {
  "use strict";
  var API = "api/";            // relativo a /api/plugins/hermes-pwa/
  var $ = function (id) { return document.getElementById(id); };
  var state = { sessions: [], current: null, messages: [], streaming: false, filter: "", pollList: null, pollMsgs: null, model: {}, attachments: [], recorder: null, recChunks: [], recTimer: null, recStart: 0, profile: "default", profiles: [], multiplex: false };

  // ───────────────────────── util
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  function toast(msg, ms) { var t = $("toast"); t.textContent = msg; t.classList.remove("hidden"); clearTimeout(t._h); t._h = setTimeout(function () { t.classList.add("hidden"); }, ms || 2600); }
  function fmtTime(ts) {
    if (!ts) return ""; var d = new Date(ts * 1000), now = new Date();
    if (d.toDateString() === now.toDateString()) return d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
    var y = new Date(now); y.setDate(now.getDate() - 1);
    if (d.toDateString() === y.toDateString()) return "ontem";
    return d.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });
  }
  function sourceLabel(s) { return ({ whatsapp: "WhatsApp", telegram: "Telegram", discord: "Discord", slack: "Slack", tui: "Terminal", cli: "Terminal", api_server: "App", dashboard: "Painel", desktop: "Desktop", cron: "Cron", hermes_browser: "Browser" })[s] || (s || "?"); }
  function initial(s) { return sourceLabel(s).charAt(0).toUpperCase(); }
  function sessionTitle(s) { return (s.title && s.title.trim()) || (s.preview && s.preview.trim().split("\n")[0].slice(0, 48)) || s.id; }
  function shortModel(m) { return (m || "").replace(/^.*\//, ""); }

  // markdown-lite seguro: escapa tudo, depois aplica blocos de código, inline code, negrito, itálico, links, listas e parágrafos
  function md(text) {
    var t = esc(text);
    var blocks = [];
    t = t.replace(/```([a-z0-9_-]*)\n([\s\S]*?)```/g, function (_, lang, code) { blocks.push("<pre><code>" + code.replace(/\n$/, "") + "</code></pre>"); return "@@BLOCK" + (blocks.length - 1) + "@@"; });
    t = t.replace(/`([^`\n]+)`/g, "<code>$1</code>");
    t = t.replace(/\*\*([^*\n]+)\*\*/g, "<b>$1</b>").replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<i>$2</i>");
    t = t.replace(/(https?:\/\/[^\s<]+[^\s<.,;:!?)])/g, '<a href="$1" target="_blank" rel="noreferrer">$1</a>');
    var lines = t.split("\n"), out = [], inList = null;
    lines.forEach(function (ln) {
      var m = ln.match(/^\s*([-*•]|\d+[.)])\s+(.*)$/);
      if (m) { var kind = /\d/.test(m[1]) ? "ol" : "ul"; if (inList !== kind) { if (inList) out.push("</" + inList + ">"); out.push("<" + kind + ">"); inList = kind; } out.push("<li>" + m[2] + "</li>"); return; }
      if (inList) { out.push("</" + inList + ">"); inList = null; }
      if (/^@@BLOCK\d+@@$/.test(ln.trim())) { out.push(ln.trim()); return; }
      if (ln.trim() === "") return;
      out.push("<p>" + ln.replace(/^#{1,6}\s+/, "") + "</p>");
    });
    if (inList) out.push("</" + inList + ">");
    return out.join("").replace(/@@BLOCK(\d+)@@/g, function (_, i) { return blocks[+i]; });
  }

  // ───────────────────────── rede
  function pq(path, profile) {  // acrescenta ?profile= quando não for o default
    var prof = profile || state.profile;
    if (!prof || prof === "default") return path;
    return path + (path.indexOf("?") >= 0 ? "&" : "?") + "profile=" + encodeURIComponent(prof);
  }
  function req(path, opts) {
    opts = opts || {};
    var init = { method: opts.method || "GET", headers: {}, credentials: "same-origin" };
    if (opts.body !== undefined) { init.headers["Content-Type"] = "application/json"; init.body = JSON.stringify(opts.body); }
    return fetch(API + path, init).then(function (r) {
      if (r.status === 401 || r.status === 403) { showLogin(); throw new Error("login"); }
      return r.text().then(function (txt) {
        var data = null; try { data = txt ? JSON.parse(txt) : null; } catch (e) { data = { raw: txt }; }
        if (!r.ok) { var d = data && (data.detail || data.error || data.message); throw new Error(typeof d === "string" ? d : (d && d.message) || ("HTTP " + r.status)); }
        return data;
      });
    });
  }

  // ───────────────────────── login embutido (sessão do dashboard expirada)
  function showLogin() { $("login").classList.remove("hidden"); }
  $("login-form").addEventListener("submit", function (e) {
    e.preventDefault(); $("login-err").textContent = "";
    fetch("/auth/password-login", { method: "POST", headers: { "Content-Type": "application/json" }, credentials: "same-origin",
      body: JSON.stringify({ provider: "basic", username: $("login-user").value.trim(), password: $("login-pass").value, next: location.pathname }) })
      .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
      .then(function (x) { if (!x.ok) { $("login-err").textContent = (x.d && x.d.detail) || "Usuário ou senha inválidos"; return; } $("login").classList.add("hidden"); boot(); })
      .catch(function () { $("login-err").textContent = "Falha de rede"; });
  });


  // ───────────────────────── diálogos próprios (sem prompt/confirm do navegador)
  function dialog(opts) {
    return new Promise(function (resolve) {
      var m = $("modal"), inp = $("modal-input"), txt = $("modal-text");
      $("modal-title").textContent = opts.title || "";
      if (opts.text) { txt.textContent = opts.text; txt.classList.remove("hidden"); } else { txt.classList.add("hidden"); }
      if (opts.input === false) { inp.classList.add("hidden"); } else { inp.classList.remove("hidden"); inp.value = opts.value || ""; inp.placeholder = opts.placeholder || ""; }
      $("modal-ok").textContent = opts.ok || "OK"; $("modal-ok").className = "btn " + (opts.danger ? "danger" : "primary");
      m.classList.remove("hidden");
      if (opts.input !== false) setTimeout(function () { inp.focus(); inp.select(); }, 30);
      function done(v) { m.classList.remove("hidden"); m.classList.add("hidden"); $("modal-form").onsubmit = null; $("modal-cancel").onclick = null; m.onclick = null; resolve(v); }
      $("modal-form").onsubmit = function (e) { e.preventDefault(); done(opts.input === false ? true : inp.value); };
      $("modal-cancel").onclick = function () { done(null); };
      m.onclick = function (e) { if (e.target === m) done(null); };
    });
  }
  function ask(title, value, placeholder, ok) { return dialog({ title: title, value: value, placeholder: placeholder, ok: ok || "Salvar" }); }
  function confirmDlg(title, text, ok) { return dialog({ title: title, text: text, input: false, ok: ok || "Confirmar", danger: true }).then(function (v) { return v === true; }); }

  // ───────────────────────── lista de sessões
  function loadSessions(silent) {
    var prof = state.profile;
    return req(pq("sessions?limit=80", prof)).then(function (d) {
      if (prof !== state.profile) return;
      state.sessions = ((d && (d.data || d.sessions)) || []).map(function (x) { x.profile = prof; return x; });
      renderSessions();
    }).catch(function (e) { if (!silent && e.message !== "login") toast("Erro ao listar: " + e.message); });
  }
  function renderSessions() {
    var ul = $("sessions"); ul.innerHTML = "";
    var f = state.filter.toLowerCase();
    var items = state.sessions.filter(function (s) { return !s.hidden && !s.archived; })
      .filter(function (s) { return !f || (sessionTitle(s) + " " + (s.preview || "") + " " + sourceLabel(s.source)).toLowerCase().indexOf(f) >= 0; })
      .sort(function (a, b) { return ((b.pinned ? 1 : 0) - (a.pinned ? 1 : 0)) || ((b.last_active || b.started_at || 0) - (a.last_active || a.started_at || 0)); });
    $("list-empty").classList.toggle("hidden", items.length > 0);
    items.forEach(function (s) {
      var li = document.createElement("li");
      if (state.current && state.current.id === s.id) li.className = "active";
      li.innerHTML = '<div class="avatar ' + esc(s.source || "") + '">' + esc(initial(s.source)) + '</div>' +
        '<div class="s-main"><div class="s-title">' + (s.pinned ? "📌 " : "") + esc(sessionTitle(s)) + '</div><div class="s-prev">' + esc((s.preview || "").replace(/\s+/g, " ").slice(0, 80) || "sem mensagens") + '</div></div>' +
        '<div class="s-meta"><span>' + esc(fmtTime(s.last_active || s.started_at)) + '</span><span class="badge">' + esc(sourceLabel(s.source)) + '</span></div>';
      var more = document.createElement("button"); more.type = "button"; more.className = "more"; more.setAttribute("aria-label", "Opções"); more.innerHTML = "&#8943;";
      more.addEventListener("click", function (e) { e.stopPropagation(); openSheet(s); });
      li.querySelector(".s-meta").appendChild(more);
      li.addEventListener("click", function () { openSession(s); });
      ul.appendChild(li);
    });
  }
  $("search").addEventListener("input", function (e) { state.filter = e.target.value; renderSessions(); });
  $("btn-refresh").addEventListener("click", function () { loadSessions(); toast("Atualizado"); });
  $("btn-new").addEventListener("click", function () {
    ask("Nova conversa", "", "Nome (opcional)", "Criar").then(function (title) {
      if (title === null) return;
      req(pq("sessions"), { method: "POST", body: { title: title.trim() || null } }).then(function (d) {
        var s = (d && d.session) || d; s.profile = state.profile; state.sessions.unshift(s); renderSessions(); openSession(s);
      }).catch(function (e) { toast("Não criou: " + e.message); });
    });
  });

  // ───────────────────────── chat
  function openSession(s) {
    state.current = s; state.messages = [];
    $("chat-title").textContent = sessionTitle(s);
    $("chat-sub").textContent = (s.profile && s.profile !== "default" ? "Agente " + s.profile + " · " : "") + sourceLabel(s.source) + (s.model ? " · " + shortModel(s.model) : (function () { var pr = state.profiles.filter(function (x) { return x.name === (s.profile || "default"); })[0]; var m = (pr && pr.model) || state.model.default; return m ? " · " + shortModel(m) : ""; })());
    $("messages").innerHTML = "";
    $("chat").classList.remove("hidden"); $("list").classList.add("hidden");
    renderSessions();
    loadMessages();
    clearInterval(state.pollMsgs); state.pollMsgs = setInterval(function () { if (!state.streaming && state.current) loadMessages(true); }, 12000);
    setTimeout(function () { $("input").focus(); }, 50);
  }
  function closeSession() {
    state.current = null; clearInterval(state.pollMsgs);
    $("chat").classList.add("hidden"); $("list").classList.remove("hidden"); renderSessions();
  }
  $("btn-back").addEventListener("click", closeSession);
  function loadMessages(silent) {
    if (!state.current) return;
    var id = state.current.id;
    return req(pq("sessions/" + encodeURIComponent(id) + "/messages", state.current.profile)).then(function (d) {
      if (!state.current || state.current.id !== id) return;
      var list = ((d && d.data) || []).filter(function (m) { return (m.role === "user" || m.role === "assistant") && m.content && String(m.content).trim(); });
      var last = function (a) { return a.length ? a[a.length - 1].id : null; };
      var changed = list.length !== state.messages.length || last(list) !== last(state.messages);
      state.messages = list;
      if (changed || !silent) renderMessages();
    }).catch(function (e) { if (!silent && e.message !== "login") toast("Erro ao carregar: " + e.message); });
  }

  // Blocos que o app coloca no texto da mensagem (o agente lê tudo como texto):
  //   🎤 Áudio (12s): /opt/data/home/uploads/xxx.webm
  //   Transcrição: ...
  //   📎 Arquivo: /opt/data/home/uploads/yyy.pdf (nome, 1.2 MB)
  function parseUserText(text) {
    var out = { voices: [], files: [], text: "" }, rest = [];
    var lines = (text || "").split("\n"), i = 0;
    while (i < lines.length) {
      var ln = lines[i];
      var mv = ln.match(/^🎤 Áudio(?: \((\d+)s\))?: (\S+)\s*$/);
      if (mv) {
        var v = { src: "api/uploads/" + encodeURIComponent(mv[2].split("/").pop()), transcript: "", note: "" }; i++;
        if (i < lines.length && /^Transcrição: /.test(lines[i])) { v.transcript = lines[i].replace(/^Transcrição: /, ""); i++; while (i < lines.length && lines[i] && !/^(🎤|📎|Transcrição:)/.test(lines[i]) && v.transcript && !/^Arquivos anexados/.test(lines[i])) { v.transcript += "\n" + lines[i]; i++; } }
        else if (i < lines.length && /^\(sem transcrição/.test(lines[i])) { v.note = lines[i]; i++; }
        out.voices.push(v); continue;
      }
      var mf = ln.match(/^📎 Arquivo: (\S+) \((.*)\)\s*$/);
      if (mf) { out.files.push(mf[2]); i++; continue; }
      if (/^Arquivos anexados pelo usuário/.test(ln) || /^- \/.*uploads\//.test(ln) || /^\(Os arquivos ficam em/.test(ln)) { i++; continue; }
      rest.push(ln); i++;
    }
    out.text = rest.join("\n").trim();
    return out;
  }
  function contentText(c) {
    if (typeof c === "string") return c;
    if (Array.isArray(c)) return c.filter(function (p) { return p && p.type === "text"; }).map(function (p) { return p.text || ""; }).join("\n");
    return c == null ? "" : String(c);
  }
  function contentImages(c) {
    if (!Array.isArray(c)) return [];
    return c.filter(function (p) { return p && p.type === "image_url" && p.image_url && p.image_url.url; }).map(function (p) { return p.image_url.url; });
  }
  function bubble(m) {
    var div = document.createElement("div");
    div.className = "msg " + (m.role === "user" ? "user" : m.role === "assistant" ? "assistant" : "system") + (m.error ? " error" : "");
    var imgs = (m.images || contentImages(m.content));
    var html = "";
    if (imgs.length) html += '<div class="imgs">' + imgs.map(function (u) { return '<img src="' + esc(u) + '" alt="imagem">'; }).join("") + "</div>";
    var text = contentText(m.content);
    if (m.role === "user") {
      var parsed = parseUserText(text);
      parsed.voices.forEach(function (v) {
        html += '<div class="voice"><audio controls preload="metadata" src="' + esc(v.src) + '"></audio>' +
          (v.transcript ? '<div class="transcript"><span class="tlabel">Transcrição</span>' + esc(v.transcript).replace(/\n/g, "<br>") + '</div>' : '<div class="transcript co-muted">' + esc(v.note || "sem transcrição") + '</div>') + '</div>';
      });
      if (parsed.files.length) html += '<div class="files">' + parsed.files.map(function (f) { return "📎 " + esc(f); }).join("<br>") + "</div>";
      if (parsed.text) html += "<p>" + esc(parsed.text).replace(/\n/g, "<br>") + "</p>";
    } else if (text) html += md(text);
    if (m.timestamp) html += '<span class="time">' + esc(fmtTime(m.timestamp)) + "</span>";
    div.innerHTML = html;
    div.querySelectorAll(".imgs img").forEach(function (im) { im.addEventListener("click", function () { lightbox(im.src); }); });
    return div;
  }
  function lightbox(src) {
    var lb = document.createElement("div"); lb.className = "lightbox"; lb.innerHTML = '<img src="' + esc(src) + '">';
    lb.addEventListener("click", function () { lb.remove(); }); document.body.appendChild(lb);
  }
  function renderMessages() {
    var box = $("messages"); box.innerHTML = "";
    state.messages.forEach(function (m) { box.appendChild(bubble(m)); });
    scrollBottom();
  }
  function scrollBottom() { var box = $("messages"); box.scrollTop = box.scrollHeight; }
  // Pedido de aprovação de comando: o agente fica pausado até a pessoa escolher.
  var APPROVAL_LABELS = { once: "Permitir uma vez", session: "Permitir nesta conversa", always: "Permitir sempre", deny: "Negar" };
  var APPROVAL_DONE = { once: "Permitido uma vez", session: "Permitido nesta conversa", always: "Permitido sempre", deny: "Negado" };
  function approvalCard(d, sid) {
    var prof = state.current && state.current.profile;
    var box = document.createElement("div"); box.className = "msg assistant approval";
    var choices = (d.choices && d.choices.length) ? d.choices : ["once", "deny"];
    box.innerHTML = '<div class="ap-title">O agente pede autorização para executar:</div>' +
      '<pre class="ap-cmd">' + esc(d.command || "(comando não informado)") + '</pre>' +
      (d.description ? '<div class="ap-why">Motivo do alerta: ' + esc(d.description) + '</div>' : '') +
      '<div class="ap-actions"></div><div class="ap-status"></div>';
    var actions = box.querySelector(".ap-actions"), status = box.querySelector(".ap-status"), settled = false;
    function lock(text, cls) { settled = true; actions.remove(); status.textContent = text; status.className = "ap-status " + (cls || ""); }
    choices.forEach(function (c) {
      if (!APPROVAL_LABELS[c]) return;
      var b = document.createElement("button"); b.type = "button"; b.textContent = APPROVAL_LABELS[c];
      b.className = "ap-btn" + (c === "deny" ? " deny" : (c === "once" ? " primary" : ""));
      b.onclick = function () {
        if (settled) return;
        Array.prototype.forEach.call(actions.querySelectorAll("button"), function (x) { x.disabled = true; });
        status.textContent = "enviando…";
        fetch(API + pq("runs/" + encodeURIComponent(d.run_id) + "/approval", prof), { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ choice: c, request_id: d.request_id || null }) })
          .then(function (r) { if (r.status === 401) { showLogin(); throw new Error("faça login de novo"); } if (!r.ok) return r.text().then(function (t) { throw new Error(r.status === 409 ? "o pedido já expirou" : (t.slice(0, 160) || ("HTTP " + r.status))); }); return r.json(); })
          .then(function () { lock(APPROVAL_DONE[c], c === "deny" ? "denied" : "ok"); setTyping(true, c === "deny" ? "pensando…" : "executando…"); })
          .catch(function (e) {
            if (settled) return;
            status.textContent = "Não foi possível enviar: " + e.message; status.className = "ap-status denied";
            Array.prototype.forEach.call(actions.querySelectorAll("button"), function (x) { x.disabled = false; });
          });
      };
      actions.appendChild(b);
    });
    $("messages").appendChild(box); scrollBottom();
    return { expire: function () { if (!settled) lock("Pedido encerrado sem resposta.", "denied"); } };
  }

  function setTyping(on, text) { $("typing").classList.toggle("hidden", !on); if (text) $("typing-text").textContent = text; }

  var input = $("input");
  input.addEventListener("input", function () { input.style.height = "auto"; input.style.height = Math.min(input.scrollHeight, 140) + "px"; });
  input.addEventListener("keydown", function (e) { if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); $("composer").requestSubmit(); } });
  $("composer").addEventListener("submit", function (e) { e.preventDefault(); send(); });

  function send() {
    var text = input.value.trim();
    var atts = state.attachments.slice();
    if ((!text && !atts.length) || state.streaming || !state.current) return;
    if (atts.some(function (a) { return a.kind === "image" && !a.url; })) { toast("Aguarde o processamento da imagem"); return; }
    input.value = ""; input.style.height = "auto"; state.attachments = []; renderTray();
    var sid = state.current.id;
    var images = atts.filter(function (a) { return a.kind === "image"; }).map(function (a) { return a.url; });
    var audios = atts.filter(function (a) { return a.kind === "audio"; });
    var files = atts.filter(function (a) { return a.kind === "file"; });

    // bolha local imediata (player com blob local enquanto sobe)
    var localLines = [];
    audios.forEach(function (a) { a.localUrl = URL.createObjectURL(a.file); });
    var userMsg = { role: "user", content: text, images: images, timestamp: Date.now() / 1000 };
    var el = bubble(userMsg);
    if (audios.length || files.length) {
      var extra = "";
      audios.forEach(function (a) { extra += '<div class="voice"><audio controls preload="metadata" src="' + esc(a.localUrl) + '"></audio><div class="transcript co-muted">transcrevendo…</div></div>'; });
      if (files.length) extra += '<div class="files">' + files.map(function (f) { return "📎 " + esc(f.name + ", " + fmtSize(f.size)); }).join("<br>") + "</div>";
      el.insertAdjacentHTML("afterbegin", extra);
    }
    state.messages.push(userMsg); $("messages").appendChild(el); scrollBottom();
    var bot = { role: "assistant", content: "", timestamp: null }; var botEl = null;
    state.streaming = true; $("btn-send").disabled = true; setTyping(true, (audios.length || files.length) ? "enviando anexos…" : "pensando…");

    var prep = Promise.all([
      Promise.all(audios.map(function (a) {
        return Promise.all([uploadAttachment(a), transcribe(a.file, a.mime || a.file.type).catch(function () { return ""; })]).then(function (r) { return { up: r[0], transcript: (r[1] || "").trim(), att: a }; });
      })),
      Promise.all(files.map(uploadAttachment))
    ]).then(function (r) {
      var voices = r[0], ups = r[1];
      var body = text;
      voices.forEach(function (v, k) {
        var dur = (v.att.name.match(/audio-(\d+)s/) || [])[1];
        body += (body ? "\n" : "") + "🎤 Áudio" + (dur ? " (" + dur + "s)" : "") + ": " + v.up.path + "\n" + (v.transcript ? "Transcrição: " + v.transcript : "(sem transcrição disponível; é uma mensagem de voz, transcreva se possível)");
        var t = el.querySelectorAll(".voice .transcript")[k];
        if (t) { t.className = "transcript" + (v.transcript ? "" : " co-muted"); t.innerHTML = v.transcript ? '<span class="tlabel">Transcrição</span>' + esc(v.transcript) : "sem transcrição"; }
      });
      ups.forEach(function (u) { body += (body ? "\n" : "") + "📎 Arquivo: " + u.path + " (" + u.name + ", " + fmtSize(u.size) + ")"; });
      if (ups.length) body += "\n(Os arquivos ficam em ~/uploads; leia com suas ferramentas de arquivo.)";
      userMsg.content = body;
      if (!images.length) return body || "Veja os anexos.";
      var parts = [{ type: "text", text: body || (images.length > 1 ? "Veja as imagens anexadas." : "Veja a imagem anexada.") }];
      images.forEach(function (u) { parts.push({ type: "image_url", image_url: { url: u } }); });
      return parts;
    });
    var approvals = [];
    function handle(ev, data) {
      var d = {}; try { d = JSON.parse(data); } catch (e) { }
      if (ev === "assistant.completed" || ev === "done" || ev === "error") approvals.forEach(function (c) { c.expire(); });
      if (ev === "assistant.delta") {
        bot.content += d.delta || "";
        if (!botEl) { botEl = bubble(bot); $("messages").appendChild(botEl); }
        botEl.innerHTML = md(bot.content); scrollBottom(); setTyping(true, "escrevendo…");
      } else if (ev === "approval.request") {
        approvals.push(approvalCard(d, sid)); setTyping(true, "aguardando sua aprovação…");
      } else if (ev === "tool.progress") {
        var tn = d.tool_name || ""; setTyping(true, tn === "_thinking" ? "pensando…" : ("usando " + tn + "…"));
      } else if (ev === "assistant.completed") {
        if (d.content) bot.content = d.content;
        bot.timestamp = Date.now() / 1000;
        if (!botEl) { botEl = bubble(bot); $("messages").appendChild(botEl); }
        botEl.innerHTML = md(bot.content) + '<span class="time">' + esc(fmtTime(bot.timestamp)) + "</span>"; scrollBottom();
      } else if (ev === "error") {
        var msg = (d.message && (d.message.detail || d.message)) || d.error || "erro";
        $("messages").appendChild(bubble({ role: "assistant", content: typeof msg === "string" ? msg : JSON.stringify(msg), error: true })); scrollBottom();
      }
    }

    prep.then(function (message) {
      setTyping(true, "pensando…");
      return fetch(API + pq("sessions/" + encodeURIComponent(sid) + "/chat/stream", state.current && state.current.profile), { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json", "Accept": "text/event-stream" }, body: JSON.stringify({ message: message }) });
    })
      .then(function (r) {
        if (r.status === 401) { showLogin(); throw new Error("login"); }
        if (!r.ok || !r.body) return r.text().then(function (t) { throw new Error(t.slice(0, 200) || ("HTTP " + r.status)); });
        var reader = r.body.getReader(), dec = new TextDecoder(), buf = "";
        function pump() {
          return reader.read().then(function (x) {
            if (x.done) return;
            buf += dec.decode(x.value, { stream: true });
            var parts = buf.split("\n\n"); buf = parts.pop();
            parts.forEach(function (chunk) {
              var ev = "message", data = "";
              chunk.split("\n").forEach(function (ln) { if (ln.indexOf("event:") === 0) ev = ln.slice(6).trim(); else if (ln.indexOf("data:") === 0) data += ln.slice(5).trim(); });
              if (data) handle(ev, data);
            });
            return pump();
          });
        }
        return pump();
      })
      .catch(function (e) { if (e.message !== "login") { $("messages").appendChild(bubble({ role: "assistant", content: "Falha: " + e.message, error: true })); scrollBottom(); } })
      .finally(function () {
        state.streaming = false; $("btn-send").disabled = false; setTyping(false);
        if (bot.content) state.messages.push(bot);
        var s = null; for (var i = 0; i < state.sessions.length; i++) if (state.sessions[i].id === sid) s = state.sessions[i];
        if (s) { s.preview = bot.content || text || "📎 anexo"; s.last_active = Date.now() / 1000; s.message_count = (s.message_count || 0) + 2; }
        renderSessions();
      });
  }


  // ───────────────────────── anexos (imagens, arquivos, prints colados, áudio)
  var MAX_IMG_SIDE = 1600, MAX_IMAGES = 6, MAX_FILE = 25 * 1024 * 1024;
  function fmtSize(n) { return n < 1024 ? n + " B" : n < 1048576 ? (n / 1024).toFixed(0) + " KB" : (n / 1048576).toFixed(1) + " MB"; }
  function readAsDataURL(file) { return new Promise(function (res, rej) { var r = new FileReader(); r.onload = function () { res(r.result); }; r.onerror = rej; r.readAsDataURL(file); }); }
  function shrinkImage(file) {
    return readAsDataURL(file).then(function (url) {
      return new Promise(function (res) {
        var im = new Image();
        im.onload = function () {
          var w = im.naturalWidth, h = im.naturalHeight, k = Math.min(1, MAX_IMG_SIDE / Math.max(w, h));
          if (k === 1 && file.size < 900 * 1024 && file.type !== "image/heic") return res(url);
          var c = document.createElement("canvas"); c.width = Math.round(w * k); c.height = Math.round(h * k);
          c.getContext("2d").drawImage(im, 0, 0, c.width, c.height);
          res(c.toDataURL("image/jpeg", 0.85));
        };
        im.onerror = function () { res(url); };
        im.src = url;
      });
    });
  }
  function addFiles(files) {
    var list = Array.prototype.slice.call(files || []);
    list.forEach(function (f) {
      if (!f) return;
      if (f.size > MAX_FILE) { toast(f.name + ": maior que 25 MB"); return; }
      if (f.type.indexOf("image/") === 0) {
        if (state.attachments.filter(function (a) { return a.kind === "image"; }).length >= MAX_IMAGES) { toast("Máximo de " + MAX_IMAGES + " imagens por mensagem"); return; }
        var item = { kind: "image", name: f.name || "imagem.jpg", size: f.size, url: null };
        state.attachments.push(item); renderTray();
        shrinkImage(f).then(function (u) { item.url = u; renderTray(); });
      } else {
        var it = { kind: f.type.indexOf("audio/") === 0 ? "audio" : "file", name: f.name || "arquivo", size: f.size, file: f, mime: f.type };
        state.attachments.push(it); renderTray();
      }
    });
  }
  function renderTray() {
    var tray = $("tray"); tray.innerHTML = "";
    tray.classList.toggle("hidden", state.attachments.length === 0);
    state.attachments.forEach(function (a, i) {
      var d = document.createElement("div"); d.className = "att " + a.kind;
      if (a.kind === "image") d.innerHTML = (a.url ? '<img src="' + esc(a.url) + '">' : '<span class="att-name">processando…</span>');
      else d.innerHTML = '<span>' + (a.kind === "audio" ? "🎤" : "📎") + '</span><span class="att-name">' + esc(a.name) + ' · ' + fmtSize(a.size) + '</span>';
      var x = document.createElement("button"); x.type = "button"; x.className = "att-x"; x.textContent = "×"; x.setAttribute("aria-label", "Remover");
      x.addEventListener("click", function () { state.attachments.splice(i, 1); renderTray(); });
      d.appendChild(x); tray.appendChild(d);
    });
  }
  $("btn-attach").addEventListener("click", function () { $("file").click(); });
  $("file").addEventListener("change", function (e) { addFiles(e.target.files); e.target.value = ""; });
  document.addEventListener("paste", function (e) {
    if (!state.current) return;
    var items = (e.clipboardData && e.clipboardData.items) || [];
    var files = [];
    for (var i = 0; i < items.length; i++) if (items[i].kind === "file") { var f = items[i].getAsFile(); if (f) files.push(f); }
    if (files.length) { e.preventDefault(); addFiles(files); toast(files.length === 1 ? "Imagem colada" : files.length + " arquivos colados"); }
  });
  ["dragenter", "dragover"].forEach(function (ev) { document.addEventListener(ev, function (e) { if (!state.current) return; e.preventDefault(); document.body.classList.add("dropping"); }); });
  ["dragleave", "drop"].forEach(function (ev) { document.addEventListener(ev, function (e) { e.preventDefault(); if (ev === "dragleave" && e.relatedTarget) return; document.body.classList.remove("dropping"); if (ev === "drop" && state.current && e.dataTransfer) addFiles(e.dataTransfer.files); }); });

  function uploadAttachment(a) {
    return readAsDataURL(a.file).then(function (url) {
      return req("upload", { method: "POST", body: { name: a.name, data_url: url, kind: a.kind } });
    });
  }
  function transcribe(blob, mime) {
    return readAsDataURL(blob).then(function (url) {
      return fetch("/api/audio/transcribe", { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ data_url: url, mime_type: mime }) })
        .then(function (r) { return r.ok ? r.json() : r.json().then(function (d) { throw new Error((d && d.detail) || ("HTTP " + r.status)); }); })
        .then(function (d) { return (d && d.transcript) || ""; });
    });
  }

  // microfone
  function stopTimer() { clearInterval(state.recTimer); state.recTimer = null; }
  function toggleRecord() {
    if (state.recorder && state.recorder.state === "recording") { state.recorder.stop(); return; }
    if (!navigator.mediaDevices || !window.MediaRecorder) { toast("Gravação não suportada neste navegador"); return; }
    navigator.mediaDevices.getUserMedia({ audio: true }).then(function (stream) {
      var mime = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg"].filter(function (m) { return MediaRecorder.isTypeSupported(m); })[0] || "";
      var rec = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
      state.recorder = rec; state.recChunks = []; state.recStart = Date.now();
      rec.ondataavailable = function (e) { if (e.data && e.data.size) state.recChunks.push(e.data); };
      rec.onstop = function () {
        stream.getTracks().forEach(function (t) { t.stop(); });
        stopTimer(); $("rec").classList.add("hidden"); $("btn-mic").classList.remove("recording");
        var type = rec.mimeType || mime || "audio/webm";
        var blob = new Blob(state.recChunks, { type: type }); state.recorder = null;
        if (blob.size < 1500) { toast("Gravação muito curta"); return; }
        var dur = Math.round((Date.now() - state.recStart) / 1000);
        attachAudio(blob, type, dur);
        if (!state.streaming) send(); else toast("Áudio anexado; envie quando a resposta terminar");
      };
      rec.start(250);
      $("btn-mic").classList.add("recording"); $("rec").classList.remove("hidden"); $("rec-time").textContent = "0:00";
      state.recTimer = setInterval(function () { var t = Math.round((Date.now() - state.recStart) / 1000); $("rec-time").textContent = Math.floor(t / 60) + ":" + ("0" + (t % 60)).slice(-2); if (t >= 300) rec.stop(); }, 500);
    }).catch(function (err) { var n = err && err.name; toast(n === "NotFoundError" ? "Nenhum microfone encontrado" : n === "NotAllowedError" ? "Permissão de microfone negada" : "Microfone indisponível: " + (err && err.message || n)); });
  }
  function attachAudio(blob, type, dur) {
    var ext = type.indexOf("mp4") >= 0 ? "m4a" : type.indexOf("ogg") >= 0 ? "ogg" : "webm";
    var f = new File([blob], "audio-" + dur + "s." + ext, { type: type.split(";")[0] });
    state.attachments.push({ kind: "audio", name: f.name, size: f.size, file: f, mime: f.type }); renderTray();
  }
  $("btn-mic").addEventListener("click", toggleRecord);

  // ───────────────────────── menu da conversa
  function openSheet(target) {
    state.sheetTarget = target;
    $("sheet").querySelector('[data-act=reload]').classList.toggle("hidden", !(state.current && state.current.id === target.id));
    $("sheet").querySelector(".sheet-title").textContent = sessionTitle(target);
    $("sheet").classList.remove("hidden");
  }
  $("btn-menu").addEventListener("click", function () { if (state.current) openSheet(state.current); });
  $("sheet").addEventListener("click", function (e) {
    var act = e.target.getAttribute && e.target.getAttribute("data-act");
    if (e.target === $("sheet") || act === "close") { $("sheet").classList.add("hidden"); return; }
    if (!act || !state.sheetTarget) return;
    $("sheet").classList.add("hidden");
    var s = state.sheetTarget; var isOpen = state.current && state.current.id === s.id;
    if (act === "rename") {
      ask("Renomear conversa", sessionTitle(s), "Novo nome").then(function (t) {
        if (t === null) return;
        req(pq("sessions/" + encodeURIComponent(s.id), s.profile), { method: "PATCH", body: { title: t.trim() } }).then(function () { s.title = t.trim(); if (isOpen) $("chat-title").textContent = sessionTitle(s); renderSessions(); toast("Renomeada"); }).catch(function (e) { toast("Não renomeou: " + e.message); });
      });
    } else if (act === "delete") {
      confirmDlg("Apagar conversa", "Isso remove o histórico desta conversa no servidor. Não dá para desfazer.", "Apagar").then(function (ok) {
        if (!ok) return;
        req(pq("sessions/" + encodeURIComponent(s.id), s.profile), { method: "DELETE" }).then(function () { state.sessions = state.sessions.filter(function (x) { return x.id !== s.id; }); if (isOpen) closeSession(); else renderSessions(); toast("Apagada"); }).catch(function (e) { toast("Não apagou: " + e.message); });
      });
    } else if (act === "reload") { loadMessages(); toast("Recarregado"); }
  });


  // ───────────────────────── agentes (perfis)
  function loadProfiles() {
    return req("profiles").then(function (d) {
      state.profiles = (d && d.profiles) || []; state.multiplex = !!(d && d.multiplex);
      var sel = $("agent"); sel.innerHTML = "";
      state.profiles.forEach(function (p) {
        var o = document.createElement("option"); o.value = p.name;
        o.textContent = p.name + (p.description ? " — " + p.description.slice(0, 40) : "");
        sel.appendChild(o);
      });
      if (!state.profiles.some(function (p) { return p.name === state.profile; })) state.profile = "default";
      sel.value = state.profile; updateAgentModel();
      $("agentbar") && null;
      document.querySelector(".agentbar").classList.toggle("hidden", state.profiles.length < 2);
    }).catch(function () { });
  }
  function updateAgentModel() {
    var p = state.profiles.filter(function (x) { return x.name === state.profile; })[0];
    $("agent-model").textContent = p ? shortModel(p.model || "") : "";
  }
  $("agent").addEventListener("change", function (e) {
    var name = e.target.value;
    if (name !== "default" && !state.multiplex) { toast("Ligue gateway.multiplex_profiles para usar outros agentes"); e.target.value = state.profile; return; }
    state.profile = name; try { localStorage.setItem("hermes-pwa-profile", name); } catch (x) { }
    updateAgentModel(); state.sessions = []; renderSessions(); loadSessions();
  });

  // ───────────────────────── boot
  function boot() {
    try { state.profile = localStorage.getItem("hermes-pwa-profile") || "default"; } catch (x) { }
    req("me").then(function (d) { state.model = (d && d.model) || {}; }).catch(function () { });
    loadProfiles().then(loadSessions);
    clearInterval(state.pollList); state.pollList = setInterval(function () { if (!state.current || $("chat").classList.contains("hidden")) loadSessions(true); }, 30000);
  }
  if ("serviceWorker" in navigator) { navigator.serviceWorker.register("sw.js", { scope: "./" }).catch(function () { }); }
  document.addEventListener("visibilitychange", function () { if (!document.hidden) { if (state.current) loadMessages(true); else loadSessions(true); } });
  boot();
})();
