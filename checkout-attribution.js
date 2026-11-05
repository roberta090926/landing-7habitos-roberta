/* Atribuição do checkout 7 Hábitos.
 * Não instala pixel, não grava cookies/localStorage e não lê dados pessoais.
 * Mantém o endereço da oferta, parâmetros preexistentes (ex: split=1)
 * e adiciona apenas UTMs de campanha válidas + SCK do produtor.
 */
(function (w, d) {
  "use strict";
  var checkoutOrigin = "https://pay.hotmart.com";
  var checkoutPath = "/D108002435X";
  var keys = ["utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term"];

  function valid(value) {
    if (typeof value !== "string" || value.length < 1 || value.length > 80) return null;
    // Não transportar dados pessoais ou parâmetros arbitrários à Hotmart.
    return /^[A-Za-z0-9._-]+$/.test(value) ? value : null;
  }

  function tags(search) {
    var p = new URLSearchParams(search || "");
    var result = {};
    keys.forEach(function (key) {
      var value = valid(p.get(key));
      if (value) result[key] = value;
    });
    return result;
  }

  function slug(s) {
    return String(s || "").toLowerCase()
      .replace(/[^a-z0-9-]+/g, "-").replace(/-+/g, "-").replace(/^-|-$/g, "");
  }

  function sck(campaign) {
    // Hotmart recomenda manter o código curto, sem underscore.
    var source = slug(campaign.utm_source || "landing").slice(0, 14);
    var medium = slug(campaign.utm_medium || "").slice(0, 12);
    var name = "r7-" + source + (medium ? "-" + medium : "");
    return name.slice(0, 30);
  }

  function checkoutUrl(original, search) {
    var url;
    try { url = new URL(original); } catch (_) { return original; }
    if (url.origin !== checkoutOrigin || url.pathname !== checkoutPath) return original;

    var campaign = tags(search);
    keys.forEach(function (key) {
      if (campaign[key] && !url.searchParams.has(key)) {
        url.searchParams.set(key, campaign[key]);
      }
    });
    if (!url.searchParams.has("sck")) url.searchParams.set("sck", sck(campaign));
    return url.href;
  }

  function apply() {
    var anchors = d.querySelectorAll("a[href]");
    Array.prototype.forEach.call(anchors, function (a) {
      var current = a.getAttribute("href");
      if (current) a.href = checkoutUrl(current, w.location.search);
    });
  }

  // Apenas para testes e auditoria; não envia dados a qualquer servidor.
  w.RBCheckoutAttribution = { checkoutUrl: checkoutUrl, tags: tags };
  if (d.readyState === "loading") d.addEventListener("DOMContentLoaded", apply);
  else apply();
})(window, document);
