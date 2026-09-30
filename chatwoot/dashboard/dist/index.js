(function () {
  "use strict";
  var SDK = window.__HERMES_PLUGIN_SDK__;
  if (!SDK || !window.__HERMES_PLUGINS__) return;
  var React = SDK.React, h = React.createElement, C = SDK.components;
  var useState = SDK.hooks.useState, useEffect = SDK.hooks.useEffect;
  var BASE = "/api/plugins/chatwoot/";
  var ORIGIN = window.location.origin;

  function api(path, opts) { return SDK.fetchJSON(BASE + path, opts); }
  function post(path, body) { return api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }); }
  function errText(e) {
    var m = e && (e.detail || e.message);
    if (m && typeof m === "object") m = m.detail || JSON.stringify(m);
    m = String(m || "Erro inesperado.");
    var j = m.match(/\{"detail":"(.*)"\}/);
    return j ? j[1] : m;
  }
  function field(label, input, hint) {
    return h("label", { className: "cw-field" }, h("span", { className: "cw-label" }, label), input,
      hint ? h("span", { className: "cw-hint" }, hint) : null);
  }

  function ChatwootPage() {
    var _st = useState(null), st = _st[0], setSt = _st[1];
    var _msg = useState(null), msg = _msg[0], setMsg = _msg[1];
    var _busy = useState(""), busy = _busy[0], setBusy = _busy[1];
    var _edit = useState(false), editing = _edit[0], setEditing = _edit[1];
    var _manual = useState(false), manual = _manual[0], setManual = _manual[1];
    var _f = useState({ base_url: "", account_id: "", access_token: "", bot_name: "Hermes", bot_token: "", profile: "default" }), f = _f[0], setF = _f[1];
    var _inb = useState(null), inboxes = _inb[0], setInboxes = _inb[1];
    var _sel = useState({}), sel = _sel[0], setSel = _sel[1];
    var _bh = useState(null), bh = _bh[0], setBh = _bh[1];   // regras de quando o agente responde

    function set(k) { return function (e) { var v = e.target.value; setF(function (o) { var n = Object.assign({}, o); n[k] = v; return n; }); }; }
    function load() {
      return api("config?origin=" + encodeURIComponent(ORIGIN)).then(function (d) {
        setSt(d);
        setBh(function (cur) { return cur || d.behavior || { reply_open: false, stop_when_assigned: true, off_label: "sem-bot" }; });
        setF(function (o) { return Object.assign({}, o, { base_url: o.base_url || d.base_url || "", account_id: o.account_id || d.account_id || "", profile: d.profile || "default" }); });
        return d;
      });
    }
    useEffect(function () { load().catch(function (e) { setMsg({ ok: false, text: errText(e) }); }); }, []);

    function run(label, promise, okText) {
      setBusy(label); setMsg(null);
      return promise.then(function (d) { if (okText) setMsg({ ok: true, text: okText }); return d; })
        .catch(function (e) { setMsg({ ok: false, text: errText(e) }); throw e; })
        .then(function (d) { setBusy(""); return d; }, function (e) { setBusy(""); throw e; });
    }

    // Reinicia o gateway e espera o canal começar a escutar.
    function restartAndWait() {
      setBusy("Reiniciando o gateway…");
      return post("restart", {}).catch(function () { return SDK.fetchJSON("/api/gateway/restart", { method: "POST" }).catch(function () { }); })
        .then(function () {
          var tries = 0;
          function poll() {
            return new Promise(function (r) { setTimeout(r, 3000); }).then(load).catch(function () { return null; }).then(function (d) {
              tries += 1;
              if (d && d.listening) { setBusy(""); setMsg({ ok: true, text: "Canal Chatwoot no ar. Mande uma mensagem pela caixa de entrada para testar." }); return; }
              if (tries >= 25) { setBusy(""); setMsg({ ok: false, text: "Configuração salva, mas o canal ainda não respondeu. Reinicie o gateway pelo menu e confira os logs." }); return; }
              return poll();
            });
          }
          return poll();
        });
    }

    function findInboxes() {
      run("Buscando caixas de entrada…", post("inboxes", { base_url: f.base_url, account_id: parseInt(f.account_id, 10) || 0, access_token: f.access_token }))
        .then(function (d) { setInboxes(d.inboxes || []); setSel({}); if (!(d.inboxes || []).length) setMsg({ ok: false, text: "Essa conta não tem caixas de entrada." }); })
        .catch(function () { });
    }
    function connect() {
      var ids = Object.keys(sel).filter(function (k) { return sel[k]; }).map(function (k) { return parseInt(k, 10); });
      run("Criando o bot no Chatwoot…", post("setup", { base_url: f.base_url, account_id: parseInt(f.account_id, 10) || 0, access_token: f.access_token, inbox_ids: ids, bot_name: f.bot_name, profile: f.profile, origin: ORIGIN }))
        .then(function (d) { setSt(d); setEditing(false); setInboxes(null); setF(function (o) { return Object.assign({}, o, { access_token: "" }); }); return restartAndWait(); })
        .catch(function () { });
    }
    function saveManual() {
      run("Salvando…", post("manual", { base_url: f.base_url, bot_token: f.bot_token, profile: f.profile, origin: ORIGIN }))
        .then(function (d) { setSt(d); setEditing(false); setF(function (o) { return Object.assign({}, o, { bot_token: "" }); }); return restartAndWait(); })
        .catch(function () { });
    }
    function changeProfile(e) {
      var p = e.target.value;
      run("Salvando…", post("profile", { profile: p })).then(function (d) { setSt(d); return restartAndWait(); }).catch(function () { });
    }
    function saveBehavior() {
      run("Salvando…", post("behavior", bh)).then(function (d) { setSt(d); setBh(d.behavior); return restartAndWait(); }).catch(function () { });
    }
    function setB(k, v) { setBh(function (o) { var n = Object.assign({}, o); n[k] = v; return n; }); }
    function disconnect() {
      run("Removendo…", api("config", { method: "DELETE" }), "Configuração removida do Hermes. O bot continua existindo no Chatwoot; desligue-o da caixa de entrada por lá.")
        .then(function (d) { setSt(d); return post("restart", {}).catch(function () { }); })
        .catch(function () { });
    }
    function copy(t) { if (navigator.clipboard) navigator.clipboard.writeText(t); setMsg({ ok: true, text: "Endereço copiado." }); }

    var agentSelect = function (value, onChange) {
      return h("select", { className: "cw-select", value: value, disabled: !!busy, onChange: onChange },
        ((st && st.profiles) || ["default"]).map(function (p) { return h("option", { key: p, value: p }, p); }));
    };

    var notice = busy ? h("p", { className: "cw-msg cw-muted" }, busy)
      : (msg ? h("p", { className: "cw-msg " + (msg.ok ? "cw-ok" : "cw-err") }, msg.text) : null);

    var connected = st && st.configured && !editing;

    var statusCard = connected ? h(C.Card, null,
      h(C.CardHeader, null, h(C.CardTitle, null, "Conexão")),
      h(C.CardContent, null,
        h("p", { className: "cw-status " + (st.listening ? "cw-ok" : "cw-err") },
          st.listening ? "Conectado e recebendo mensagens" : "Configurado, mas o canal não está no ar"),
        h("dl", { className: "cw-dl" },
          h("dt", null, "Chatwoot"), h("dd", null, st.base_url),
          st.bot_name ? h("dt", null, "Bot") : null, st.bot_name ? h("dd", null, st.bot_name + (st.account_id ? " (conta " + st.account_id + ")" : "")) : null,
          (st.inboxes || []).length ? h("dt", null, "Caixas de entrada") : null, (st.inboxes || []).length ? h("dd", null, st.inboxes.join(", ")) : null,
          h("dt", null, "Token do bot"), h("dd", null, st.token_preview || "—"),
          h("dt", null, "Agente que atende"), h("dd", null, agentSelect(st.profile, changeProfile)),
          h("dt", null, "Webhook"), h("dd", null, h("span", { className: "cw-mono" }, st.webhook_url || "—"))
        ),
        h("div", { className: "cw-actions" },
          !st.listening ? h(C.Button, { onClick: function () { restartAndWait(); }, disabled: !!busy }, "Reiniciar gateway") : null,
          st.webhook_url ? h(C.Button, { variant: "outline", onClick: function () { copy(st.webhook_url); }, disabled: !!busy }, "Copiar webhook") : null,
          h(C.Button, { variant: "outline", onClick: function () { setEditing(true); setMsg(null); }, disabled: !!busy }, "Reconfigurar"),
          h(C.Button, { variant: "outline", onClick: disconnect, disabled: !!busy }, "Desconectar")
        ),
        notice
      )
    ) : null;

    var behaviorCard = (connected && bh) ? h(C.Card, null,
      h(C.CardHeader, null, h(C.CardTitle, null, "Quando o agente responde")),
      h(C.CardContent, null,
        h("div", { className: "cw-opts" },
          h("label", { className: "cw-opt" },
            h("input", { type: "radio", name: "cw-mode", checked: !bh.reply_open, disabled: !!busy, onChange: function () { setB("reply_open", false); } }),
            h("span", null, h("b", null, "Só em conversas pendentes"),
              h("span", { className: "cw-hint" }, "Quando a conversa passa para \"Aberta\", o agente para. Para devolver a ele, volte a conversa para \"Pendente\"."))),
          h("label", { className: "cw-opt" },
            h("input", { type: "radio", name: "cw-mode", checked: !!bh.reply_open, disabled: !!busy, onChange: function () { setB("reply_open", true); setB("stop_when_assigned", true); } }),
            h("span", null, h("b", null, "Em conversas pendentes e abertas"),
              h("span", { className: "cw-hint" }, "O agente continua respondendo mesmo com a conversa aberta.")))
        ),
        h("label", { className: "cw-check cw-sub-opt" },
          h("input", { type: "checkbox", checked: !!bh.stop_when_assigned, disabled: !!busy, onChange: function (e) { setB("stop_when_assigned", e.target.checked); } }),
          h("span", null, "Parar quando a conversa for atribuída a um atendente ou a um time")),
        bh.reply_open && !bh.stop_when_assigned ? h("p", { className: "cw-msg cw-err" }, "Assim o agente só para em conversas com a etiqueta abaixo. O atendente e o agente podem responder ao mesmo tempo.") : null,
        h("div", { className: "cw-grid" },
          field("Etiqueta que desliga o agente na conversa", h(C.Input, { value: bh.off_label, disabled: !!busy, onChange: function (e) { setB("off_label", e.target.value); } }),
            "Conversa com essa etiqueta nunca é respondida pelo agente, em qualquer situação. Tire a etiqueta para ele voltar.")),
        bh.reply_open ? h("p", { className: "cw-muted" }, "Neste modo, quando o agente transfere para um humano ele coloca essa etiqueta na conversa, para não continuar respondendo.") : null,
        h("div", { className: "cw-actions" },
          h(C.Button, { onClick: saveBehavior, disabled: !!busy }, "Salvar regras"))
      )
    ) : null;

    var autoForm = h("div", null,
      h("div", { className: "cw-grid" },
        field("Endereço do Chatwoot", h(C.Input, { placeholder: "https://chat.seudominio.com.br", value: f.base_url, onChange: set("base_url"), disabled: !!busy })),
        field("ID da conta", h(C.Input, { placeholder: "1", value: f.account_id, onChange: set("account_id"), disabled: !!busy }), "O número que aparece no endereço: /app/accounts/1/…"),
        field("Token de acesso do administrador", h(C.Input, { type: "password", autoComplete: "off", placeholder: "token do seu perfil", value: f.access_token, onChange: set("access_token"), disabled: !!busy }),
          "No Chatwoot: Configurações do perfil > Token de acesso. É usado só agora para criar o bot e não fica guardado.")
      ),
      h("div", { className: "cw-actions" },
        h(C.Button, { onClick: findInboxes, disabled: !!busy || !f.base_url || !f.account_id || !f.access_token }, "Buscar caixas de entrada")),
      inboxes && inboxes.length ? h("div", { className: "cw-step" },
        h("p", { className: "cw-label" }, "Caixas de entrada que o agente vai atender"),
        h("div", { className: "cw-inboxes" }, inboxes.map(function (i) {
          return h("label", { key: i.id, className: "cw-check" },
            h("input", { type: "checkbox", checked: !!sel[i.id], disabled: !!busy, onChange: function (e) { var v = e.target.checked; setSel(function (o) { var n = Object.assign({}, o); n[i.id] = v; return n; }); } }),
            h("span", null, i.name), h("span", { className: "cw-muted" }, i.channel));
        })),
        h("div", { className: "cw-grid" },
          field("Nome do bot no Chatwoot", h(C.Input, { value: f.bot_name, onChange: set("bot_name"), disabled: !!busy })),
          field("Agente que atende", agentSelect(f.profile, set("profile")), "O agente (perfil) do Hermes que responde os clientes.")
        ),
        h("div", { className: "cw-actions" },
          h(C.Button, { onClick: connect, disabled: !!busy || !Object.keys(sel).some(function (k) { return sel[k]; }) }, "Conectar"))
      ) : null
    );

    var manualForm = h("div", null,
      h("p", { className: "cw-muted" }, "Use quando o bot já existe no Chatwoot. Depois de salvar, copie o webhook mostrado aqui para o campo de URL do bot e ligue o bot à caixa de entrada."),
      h("div", { className: "cw-grid" },
        field("Endereço do Chatwoot", h(C.Input, { placeholder: "https://chat.seudominio.com.br", value: f.base_url, onChange: set("base_url"), disabled: !!busy })),
        field("Token do bot", h(C.Input, { type: "password", autoComplete: "off", value: f.bot_token, onChange: set("bot_token"), disabled: !!busy })),
        field("Agente que atende", agentSelect(f.profile, set("profile")))
      ),
      h("div", { className: "cw-actions" },
        h(C.Button, { onClick: saveManual, disabled: !!busy || !f.base_url || !f.bot_token }, "Salvar"))
    );

    var setupCard = (st && !connected) ? h(C.Card, null,
      h(C.CardHeader, null, h(C.CardTitle, null, st.configured ? "Reconfigurar" : "Conectar ao Chatwoot")),
      h(C.CardContent, null,
        !st.public_base ? h("p", { className: "cw-msg cw-err" }, "O Hermes não sabe o próprio endereço público. Acesse o painel pelo domínio com HTTPS.") : null,
        h("div", { className: "cw-tabs" },
          h("button", { type: "button", className: "cw-tab" + (!manual ? " on" : ""), onClick: function () { setManual(false); } }, "Automática"),
          h("button", { type: "button", className: "cw-tab" + (manual ? " on" : ""), onClick: function () { setManual(true); } }, "Manual")),
        manual ? manualForm : autoForm,
        st.configured ? h("div", { className: "cw-actions" }, h(C.Button, { variant: "outline", onClick: function () { setEditing(false); }, disabled: !!busy }, "Cancelar")) : null,
        notice
      )
    ) : null;

    var how = h(C.Card, null,
      h(C.CardHeader, null, h(C.CardTitle, null, "Como funciona")),
      h(C.CardContent, null,
        h("ul", { className: "cw-list" },
          h("li", null, "O Hermes entra no Chatwoot como um bot. Conversas novas da caixa de entrada ficam com o bot (situação \"Pendente\") e o agente responde."),
          h("li", null, "Cada conversa do Chatwoot é uma sessão no Hermes: o agente lembra do que já foi dito nela."),
          h("li", null, "No modo padrão, quando o agente transfere ou um atendente abre a conversa, ela passa para \"Aberta\" e o agente para. Para devolver a ele, volte a conversa para \"Pendente\"."),
          h("li", null, "Em \"Quando o agente responde\" dá para fazer o agente atender também conversas abertas e parar só quando forem atribuídas a um atendente ou a um time."),
          h("li", null, "Para desligar o agente em uma conversa específica, coloque nela a etiqueta configurada (padrão: sem-bot).")
        ),
        h("p", { className: "cw-muted" }, "Atenção: quem escreve aqui são clientes. Use um agente próprio para atendimento, sem acesso ao terminal e a arquivos do servidor.")
      )
    );

    return h("div", { className: "cw-page" },
      h("div", null,
        h("h1", { className: "cw-title" }, "Chatwoot"),
        h("p", { className: "cw-sub" }, "O agente do Hermes atende os clientes nas caixas de entrada do Chatwoot e passa para um humano quando precisa.")),
      st === null ? h("p", { className: "cw-muted" }, "Carregando…") : null,
      statusCard, behaviorCard, setupCard, how);
  }

  window.__HERMES_PLUGINS__.register("chatwoot", ChatwootPage);
})();
