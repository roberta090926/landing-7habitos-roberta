/* Integração opcional para ViewContent: NÃO envia CAPI sem relay configurado.
 * O navegador continua medindo ViewContent mesmo se o servidor estiver indisponível.
 * Meta Pixel e CAPI usam o MESMO id para a mesma visualização.
 */
(function () {
  "use strict";
  function hasConsent() {
    return window.RB_META_CONSENT_GRANTED === true;
  }
  function makeEventId() {
    if (!window.crypto || typeof window.crypto.getRandomValues !== "function") return null;
    var bytes = new Uint8Array(16);
    window.crypto.getRandomValues(bytes);
    return "rbvc-" + Array.prototype.map.call(bytes, function (v) {
      return v.toString(16).padStart(2, "0");
    }).join("");
  }
  function getFbp() {
    var match = document.cookie.match(/(?:^|;\s*)_fbp=([^;]*)/);
    var value = match ? decodeURIComponent(match[1]) : null;
    return value && /^fb\.1\.\d{10,16}\.\d{5,30}$/.test(value) ? value : null;
  }

  window.rbTrackViewContentWithCapi = function (originalPixelPayload) {
    if (!hasConsent() || typeof window.fbq !== "function") return;

    var id = makeEventId();
    if (!id) {
      window.fbq("track", "ViewContent", originalPixelPayload);
      return;
    }
    // Primeiro a medição do navegador, preservando o evento já existente.
    window.fbq("track", "ViewContent", originalPixelPayload, {eventID: id});

    // O serviço ainda não existe na produção. A URL só será configurada
    // após testes e autorização explícita; nenhum pedido é feito sem ela.
    var configured = window.RB_CAPI_RELAY_ORIGIN;
    if (typeof configured !== "string" || !configured) return;
    var relay = configured.replace(/\/+$/, "");
    if (!/^https:\/\/[A-Za-z0-9.-]+(?::443)?$/.test(relay)) return;
    if (typeof window.fetch !== "function") return;

    window.fetch(relay + "/v1/view-token?event_id=" + encodeURIComponent(id), {
      method: "GET", mode: "cors", cache: "no-store",
      credentials: "omit", referrerPolicy: "no-referrer"
    }).then(function (r) {
      if (!r.ok) throw new Error("Não foi possível preparar CAPI");
      return r.json();
    }).then(function (token) {
      if (!hasConsent() || !token || token.event_id !== id ||
          !Number.isInteger(token.expires) ||
          typeof token.signature !== "string" ||
          !/^[a-f0-9]{64}$/.test(token.signature)) return;
      var body = {
        event_id: id,
        expires: token.expires,
        signature: token.signature,
        consent: true
      };
      var fbp = getFbp();
      if (fbp) body.fbp = fbp;
      // Sem nome, telefone, e-mail, estado de saúde ou detalhes de produto.
      return window.fetch(relay + "/v1/view-content", {
        method: "POST", mode: "cors", credentials: "omit",
        cache: "no-store", keepalive: true, referrerPolicy: "no-referrer",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(body)
      });
    }).catch(function () {
      // Falha no relay NÃO bloqueia o Pixel nem a compra.
    });
  };
})();
