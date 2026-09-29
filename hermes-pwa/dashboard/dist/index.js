(function () {
  "use strict";
  var SDK = window.__HERMES_PLUGIN_SDK__;
  if (!SDK || !window.__HERMES_PLUGINS__) return;
  var React = SDK.React, h = React.createElement, C = SDK.components;
  var APP = "/api/plugins/hermes-pwa/";
  var LOADED_AT = window.location.pathname;  // rota em que o painel foi carregado

  function PwaPage() {
    var url = window.location.origin + "/pwa";
    var appUrl = window.location.origin + APP;
    // Quem chega DIRETO por /pwa (digitou, QR, link do /pwa no chat) vai para o app em qualquer
    // aparelho. A página de instalação só aparece ao clicar no menu "PWA" dentro do painel
    // (navegação interna do SPA: a página foi carregada em outra rota) ou com ?stay=1.
    var params = new URLSearchParams(window.location.search);
    var direct = LOADED_AT.indexOf("/pwa") === 0;
    if (params.get("app") === "1" || (direct && params.get("stay") !== "1")) {
      window.location.replace(APP);
      return h("div", { className: "hp-page" }, h("p", { className: "hp-muted" }, "Abrindo o app…"));
    }
    var qr = APP + "qr.svg?target=" + encodeURIComponent(url);
    function copy(t) { if (navigator.clipboard) navigator.clipboard.writeText(t); }

    var install = h(C.Card, null,
      h(C.CardHeader, null, h(C.CardTitle, null, "Instalar no celular")),
      h(C.CardContent, null,
        h("div", { className: "hp-row" },
          h("img", { className: "hp-qr", src: qr, alt: "QR code do app" }),
          h("div", null,
            h("ol", { className: "hp-steps" },
              h("li", null, "Aponte a câmera do celular para o QR ou abra ", h("span", { className: "hp-link" }, url)),
              h("li", null, "Faça login com o usuário e senha do painel."),
              h("li", null, "Toque em \"Abrir app\"."),
              h("li", null, "Android (Chrome): menu ⋮ → \"Instalar app\" ou \"Adicionar à tela inicial\"."),
              h("li", null, "iPhone (Safari): botão Compartilhar → \"Adicionar à Tela de Início\".")
            ),
            h("div", { className: "hp-actions" },
              h(C.Button, { onClick: function () { window.location.href = APP; } }, "Abrir app (nesta aba)"),
                h(C.Button, { variant: "outline", onClick: function () { window.open(appUrl, "_blank"); } }, "Abrir em nova aba"),
              h(C.Button, { variant: "outline", onClick: function () { copy(url); } }, "Copiar link")
            )
          )
        )
      )
    );

    var how = h(C.Card, null,
      h(C.CardHeader, null, h(C.CardTitle, null, "Como funciona")),
      h(C.CardContent, null,
        h("p", null, "O app é servido pelo próprio dashboard em ", h("span", { className: "hp-link" }, appUrl),
          " e usa o mesmo login. As conversas vêm do API server do gateway (porta 8642): você vê e continua sessões do WhatsApp, Telegram, terminal e do painel no mesmo lugar."),
        h("p", { className: "hp-muted" }, "No chat de qualquer canal, o comando /pwa devolve este link. A sessão de login vale 12 h e se renova por 30 dias enquanto o app for usado.")
      )
    );

    return h("div", { className: "hp-page" },
      h("div", null,
        h("h1", { className: "hp-title" }, "App móvel (PWA)"),
        h("p", { className: "hp-sub" }, "Esta página é só a instalação. O app em si abre em tela cheia, sem o painel em volta, em " + appUrl + ". No celular, /pwa já abre o app direto.")
      ),
      install,
      how
    );
  }
  window.__HERMES_PLUGINS__.register("hermes-pwa", PwaPage);
})();
