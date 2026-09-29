(function () {
  "use strict";
  // codex-oauth — aba "Codex" do dashboard Hermes.
  // Fluxo OAuth device-code independente do chat: funciona mesmo sem provedor configurado.
  var SDK = window.__HERMES_PLUGIN_SDK__;
  if (!SDK || !window.__HERMES_PLUGINS__) return;

  var React = SDK.React;
  var h = React.createElement;
  var useState = SDK.hooks.useState;
  var useEffect = SDK.hooks.useEffect;
  var useRef = SDK.hooks.useRef;
  var useCallback = SDK.hooks.useCallback;
  var C = SDK.components;
  var BASE = "/api/plugins/codex-oauth";

  function api(path, method, body) {
    var opts = { method: method || "GET" };
    if (body !== undefined) {
      opts.headers = { "Content-Type": "application/json" };
      opts.body = JSON.stringify(body);
    }
    return SDK.fetchJSON(BASE + path, opts);
  }

  function errText(e) {
    if (!e) return "erro desconhecido";
    if (typeof e === "string") return e;
    return e.detail || e.message || (e.error && (e.error.detail || e.error)) || String(e);
  }


  // ───────────────────────── Claude (Anthropic) via OAuth PKCE ─────────────────────────
  function ClaudeSection() {
    var _s = useState(null), ov = _s[0], setOv = _s[1];
    var _e = useState(""), err = _e[0], setErr = _e[1];
    var _n = useState(""), notice = _n[0], setNotice = _n[1];
    var _p = useState(null), pending = _p[0], setPending = _p[1];
    var _c = useState(""), code = _c[0], setCode = _c[1];
    var _m = useState(""), model = _m[0], setModel = _m[1];
    var _b = useState(false), busy = _b[0], setBusy = _b[1];

    var refresh = useCallback(function () {
      return api("/anthropic/status").then(function (d) {
        setOv(d);
        if (d.pending_session && d.pending_session.status === "pending") setPending(d.pending_session);
        if (!model) setModel((d.model && d.model.provider === "anthropic" && d.model.default) || "claude-sonnet-4-6");
        setErr("");
      }).catch(function (e) { setErr(errText(e)); });
    }, [model]);
    useEffect(function () { refresh(); }, []);

    function start(force) {
      setBusy(true); setErr(""); setNotice("");
      api("/anthropic/start", "POST", { force: !!force }).then(function (d) { setPending(d); setCode(""); })
        .catch(function (e) { setErr(errText(e)); }).finally(function () { setBusy(false); });
    }
    function submit() {
      if (!pending) return;
      setBusy(true); setErr(""); setNotice("");
      api("/anthropic/submit", "POST", { code: code, session_id: pending.session_id }).then(function (d) {
        setPending(null); setCode("");
        setNotice("Claude conectado. Escolha o modelo abaixo e defina como padrão se quiser usar o Claude.");
        refresh();
      }).catch(function (e) { setErr(errText(e)); }).finally(function () { setBusy(false); });
    }
    function saveModel() {
      setBusy(true); setErr(""); setNotice("");
      api("/anthropic/set-model", "POST", { model: model }).then(function (d) {
        setNotice("Padrão salvo: " + d.provider + " / " + d.default + ". Abra uma sessão nova no chat (/new).");
        refresh();
      }).catch(function (e) { setErr(errText(e)); }).finally(function () { setBusy(false); });
    }
    function disconnect() {
      if (!window.confirm("Desconectar o Claude? Os tokens serão removidos.")) return;
      setBusy(true); setErr(""); setNotice("");
      api("/anthropic/disconnect", "POST", {}).then(function () { setPending(null); setNotice("Claude desconectado."); refresh(); })
        .catch(function (e) { setErr(errText(e)); }).finally(function () { setBusy(false); });
    }

    if (!ov) return h(C.Card, null, h(C.CardHeader, null, h(C.CardTitle, null, "Claude (Anthropic) via OAuth")), h(C.CardContent, null, h("p", { className: "co-muted" }, h("span", { className: "co-spin" }), "Carregando…")));
    var logged = !!ov.logged_in;
    var ready = !!ov.ready;
    var models = ov.suggested_models || ["claude-sonnet-4-6"];
    var isPending = pending && pending.status === "pending";

    return h(C.Card, null,
      h(C.CardHeader, null, h(C.CardTitle, null, "Claude (Anthropic) via OAuth")),
      h(C.CardContent, null,
        h("p", { className: "co-muted" }, "Requer plano Claude Max com créditos extras de uso. Claude Pro não é aceito pela Anthropic neste fluxo (use ANTHROPIC_API_KEY em KEYS)."),
        err && h("p", { className: "co-err" }, err),
        notice && h("p", { className: "co-ok" }, notice),
        h("dl", { className: "co-kv", style: { marginTop: "0.75rem" } },
          h("dt", null, "Conta Claude"), h("dd", null, logged ? h("span", { className: "co-ok" }, "conectada ✓", ov.token_preview ? " (…" + ov.token_preview + ")" : "", ov.kind ? " · " + ov.kind : "") : h("span", { className: "co-err" }, "não conectada")),
          h("dt", null, "Padrão ativo"), h("dd", null, ready ? h("span", { className: "co-ok" }, "anthropic / " + ov.model.default) : h("span", { className: "co-muted" }, (ov.model && ov.model.provider) ? ov.model.provider + " / " + ov.model.default : "—"))
        ),
        h("div", { className: "co-row", style: { marginTop: "0.75rem" } },
          !isPending && h(C.Button, { onClick: function () { start(false); }, disabled: busy }, logged ? "Refazer login" : "Conectar ao Claude"),
          logged && h(C.Button, { variant: "destructive", onClick: disconnect, disabled: busy }, "Desconectar"),
          h(C.Button, { variant: "ghost", onClick: refresh, disabled: busy }, "Atualizar")
        ),
        isPending && h("div", { style: { marginTop: "1rem" } },
          h("ol", { className: "co-steps" },
            h("li", null, "Abra ", h("a", { className: "co-link", href: pending.auth_url, target: "_blank", rel: "noreferrer" }, "claude.ai/oauth/authorize…"), " ",
              h(C.Button, { size: "sm", variant: "outline", onClick: function () { window.open(pending.auth_url, "_blank"); } }, "Abrir")),
            h("li", null, "Entre na conta Claude Max e clique em Autorizar."),
            h("li", null, "A Anthropic mostra um código. Cole-o aqui e confirme:")
          ),
          h("div", { className: "co-row", style: { marginTop: "0.5rem" } },
            h(C.Input, { placeholder: "cole o código (ex.: abc123#xyz…)", value: code, onChange: function (e) { setCode(e.target.value); }, style: { minWidth: "360px" } }),
            h(C.Button, { onClick: submit, disabled: busy || !code.trim() }, "Confirmar código"),
            h(C.Button, { size: "sm", variant: "ghost", onClick: function () { setPending(null); }, disabled: busy }, "Cancelar")
          ),
          h("p", { className: "co-muted" }, "Expira em ", Math.max(0, Math.floor((pending.expires_in_seconds || 0) / 60)), " min.")
        ),
        h("div", { style: { marginTop: "1rem" } },
          h("p", { className: "co-muted" }, "Modelo padrão (grava model.provider = anthropic):"),
          h("div", { className: "co-row", style: { marginTop: "0.4rem" } },
            h("select", { className: "co-select", value: model, onChange: function (e) { setModel(e.target.value); }, disabled: !logged || busy },
              models.map(function (m) { return h("option", { key: m, value: m }, m); }).concat(
                models.indexOf(model) === -1 && model ? [h("option", { key: "_custom", value: model }, model)] : [])),
            h(C.Input, { placeholder: "ou digite outro id", value: model, onChange: function (e) { setModel(e.target.value); }, disabled: !logged || busy, style: { maxWidth: "260px" } }),
            h(C.Button, { onClick: saveModel, disabled: !logged || busy || !model }, "Usar Claude como padrão")
          )
        )
      )
    );
  }

  function CodexPage() {
    var _s = useState(null), ov = _s[0], setOv = _s[1];
    var _l = useState(true), loading = _l[0], setLoading = _l[1];
    var _e = useState(""), err = _e[0], setErr = _e[1];
    var _p = useState(null), pending = _p[0], setPending = _p[1];
    var _m = useState(""), model = _m[0], setModel = _m[1];
    var _b = useState(false), busy = _b[0], setBusy = _b[1];
    var _n = useState(""), notice = _n[0], setNotice = _n[1];
    var timer = useRef(null);
    var toast = SDK.hooks.useToast ? SDK.hooks.useToast() : null;

    var refresh = useCallback(function () {
      return api("/status").then(function (d) {
        setOv(d);
        if (d.pending_session && d.pending_session.status === "pending") setPending(d.pending_session);
        if (!model) { var sug = d.suggested_models || []; setModel((d.model && d.model.default) || (sug.indexOf("gpt-5.5") >= 0 ? "gpt-5.5" : sug[0]) || "gpt-5.5"); }
        setErr("");
        return d;
      }).catch(function (e) { setErr(errText(e)); }).finally(function () { setLoading(false); });
    }, [model]);

    useEffect(function () { refresh(); }, []);

    // polling enquanto houver login pendente
    useEffect(function () {
      if (timer.current) { clearInterval(timer.current); timer.current = null; }
      if (!pending || pending.status !== "pending") return;
      timer.current = setInterval(function () {
        api("/check?session_id=" + encodeURIComponent(pending.session_id)).then(function (d) {
          setPending(d);
          if (d.status !== "pending") {
            clearInterval(timer.current); timer.current = null;
            if (d.status === "approved") {
              setNotice("Login aprovado. Tokens salvos e provedor openai-codex definido como padrão.");
              if (toast && toast.toast) toast.toast({ title: "Codex conectado" });
            }
            refresh();
          }
        }).catch(function () { /* transitório */ });
      }, 4000);
      return function () { if (timer.current) clearInterval(timer.current); };
    }, [pending && pending.session_id, pending && pending.status]);

    function start(force) {
      setBusy(true); setErr(""); setNotice("");
      api("/start", "POST", { force: !!force }).then(function (d) {
        if (d.already_connected) { setNotice("Já conectado ao Codex."); setOv(d); return; }
        setPending(d);
      }).catch(function (e) { setErr(errText(e)); }).finally(function () { setBusy(false); });
    }
    function cancel() {
      if (!pending) return;
      setBusy(true);
      api("/cancel", "POST", { session_id: pending.session_id }).then(function () { setPending(null); refresh(); })
        .catch(function (e) { setErr(errText(e)); }).finally(function () { setBusy(false); });
    }
    function saveModel() {
      setBusy(true); setErr(""); setNotice("");
      api("/set-model", "POST", { model: model }).then(function (d) {
        setNotice("Padrão salvo: " + d.provider + " / " + d.default + ". Novas sessões já usam o Codex; reinicie o gateway para Telegram/WhatsApp/etc.");
        refresh();
      }).catch(function (e) { setErr(errText(e)); }).finally(function () { setBusy(false); });
    }
    function disconnect() {
      if (!window.confirm("Desconectar o Codex? Os tokens serão removidos do auth.json.")) return;
      setBusy(true); setErr(""); setNotice("");
      api("/disconnect", "POST", {}).then(function () { setPending(null); setNotice("Codex desconectado."); refresh(); })
        .catch(function (e) { setErr(errText(e)); }).finally(function () { setBusy(false); });
    }
    function copy(text) {
      if (navigator.clipboard) navigator.clipboard.writeText(text).then(function () { setNotice("Copiado: " + text); });
    }

    if (loading) return h("div", { className: "co-page" }, h("p", { className: "co-muted" }, h("span", { className: "co-spin" }), "Carregando…"));

    var logged = !!(ov && ov.logged_in);
    var ready = !!(ov && ov.ready);
    var models = (ov && ov.suggested_models) || ["gpt-5.5"];
    var isPending = pending && pending.status === "pending";

    // ---- cartão de status
    var statusCard = h(C.Card, null,
      h(C.CardHeader, null, h(C.CardTitle, null, "Status")),
      h(C.CardContent, null,
        h("dl", { className: "co-kv" },
          h("dt", null, "Conta Codex"), h("dd", null, logged ? h("span", { className: "co-ok" }, "conectada ✓", ov.token_preview ? " (…" + ov.token_preview + ")" : "") : h("span", { className: "co-err" }, "não conectada")),
          h("dt", null, "Provedor padrão"), h("dd", null, (ov.model && ov.model.provider) || "—"),
          h("dt", null, "Modelo padrão"), h("dd", null, (ov.model && ov.model.default) || "—"),
          h("dt", null, "Pronto para uso"), h("dd", null, ready ? h("span", { className: "co-ok" }, "sim") : h("span", { className: "co-warn" }, logged ? "falta definir o provedor/modelo" : "não"))
        ),
        h("div", { className: "co-row", style: { marginTop: "1rem" } },
          !logged && !isPending && h(C.Button, { onClick: function () { start(false); }, disabled: busy }, "Conectar ao Codex"),
          logged && h(C.Button, { variant: "outline", onClick: function () { start(true); }, disabled: busy }, "Refazer login"),
          logged && h(C.Button, { variant: "destructive", onClick: disconnect, disabled: busy }, "Desconectar"),
          h(C.Button, { variant: "ghost", onClick: refresh, disabled: busy }, "Atualizar")
        )
      )
    );

    // ---- cartão do login pendente / resultado
    var loginCard = null;
    if (pending) {
      var st = pending.status;
      var body;
      if (st === "pending") {
        body = [
          h("ol", { className: "co-steps", key: "steps" },
            h("li", null, "Abra ", h("a", { className: "co-link", href: pending.verification_url, target: "_blank", rel: "noreferrer" }, pending.verification_url), " ",
              h(C.Button, { size: "sm", variant: "outline", onClick: function () { window.open(pending.verification_url, "_blank"); } }, "Abrir")),
            h("li", null, "Entre na conta ChatGPT que tem a assinatura (Plus, Pro ou Team)."),
            h("li", null, "Digite o código abaixo:")
          ),
          h("div", { className: "co-row", key: "code", style: { marginTop: "0.75rem" } },
            h("span", { className: "co-code" }, pending.user_code),
            h(C.Button, { size: "sm", variant: "outline", onClick: function () { copy(pending.user_code); } }, "Copiar código")
          ),
          h("p", { className: "co-muted", key: "wait" }, h("span", { className: "co-spin" }),
            "Aguardando aprovação… expira em ", Math.max(0, Math.floor((pending.expires_in_seconds || 0) / 60)), " min."),
          h("div", { className: "co-row", key: "actions" }, h(C.Button, { size: "sm", variant: "ghost", onClick: cancel, disabled: busy }, "Cancelar"))
        ];
      } else if (st === "approved") {
        body = [h("p", { className: "co-ok", key: "ok" }, "✓ Login aprovado e tokens salvos.")];
      } else {
        body = [
          h("p", { className: "co-err", key: "bad" }, "Login " + st + (pending.error ? ": " + pending.error : "")),
          h("div", { className: "co-row", key: "retry" }, h(C.Button, { onClick: function () { start(true); }, disabled: busy }, "Tentar novamente"))
        ];
      }
      loginCard = h(C.Card, null, h(C.CardHeader, null, h(C.CardTitle, null, "Login OAuth")), h(C.CardContent, null, body));
    }

    // ---- cartão do modelo
    var modelCard = h(C.Card, null,
      h(C.CardHeader, null, h(C.CardTitle, null, "Modelo padrão")),
      h(C.CardContent, null,
        h("p", { className: "co-muted" }, "Define model.provider = openai-codex e model.default no config.yaml."),
        h("div", { className: "co-row", style: { marginTop: "0.5rem" } },
          h("select", { className: "co-select", value: model, onChange: function (e) { setModel(e.target.value); }, disabled: !logged || busy },
            models.map(function (m) { return h("option", { key: m, value: m }, m); }).concat(
              models.indexOf(model) === -1 && model ? [h("option", { key: "_custom", value: model }, model)] : [])
          ),
          h(C.Input, { placeholder: "ou digite outro id", value: model, onChange: function (e) { setModel(e.target.value); }, disabled: !logged || busy, style: { maxWidth: "260px" } }),
          h(C.Button, { onClick: saveModel, disabled: !logged || busy || !model }, "Definir como padrão")
        ),
        !logged && h("p", { className: "co-muted", style: { marginTop: "0.5rem" } }, "Conecte a conta primeiro.")
      )
    );

    return h("div", { className: "co-page" },
      h("div", { className: "co-header" },
        h("div", null, h("h1", { className: "co-title" }, "Assinaturas via OAuth: Codex (ChatGPT) e Claude"),
          h("p", { className: "co-sub" }, "Conecte suas assinaturas sem chave de API. Funciona mesmo com o chat em \"setup required\"."))
      ),
      err && h("p", { className: "co-err" }, err),
      notice && h("p", { className: "co-ok" }, notice),
      statusCard,
      loginCard,
      modelCard,
      h(ClaudeSection, null),
      h("p", { className: "co-muted" }, "Também disponível no chat como /codex-login e /codex-status, e no terminal como hermes codex-oauth.")
    );
  }

  window.__HERMES_PLUGINS__.register("codex-oauth", CodexPage);
})();
