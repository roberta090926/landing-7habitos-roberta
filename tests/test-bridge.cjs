const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");
const source = fs.readFileSync(path.join(__dirname, "../meta-capi-bridge.js"), "utf8");

function setUp({consent = true, configured = true, fetchImpl, crypto = true} = {}) {
  const pixels = [], requests = [];
  const id = "rbvc-" + Buffer.from(Array.from({length: 16}, (_, i) => i + 1)).toString("hex");
  const window = {
    RB_META_CONSENT_GRANTED: consent,
    RB_CAPI_RELAY_ORIGIN: configured ? "https://relay.example.test" : undefined,
    fbq: (...a) => pixels.push(a),
    fetch: (...args) => {
      requests.push(args);
      return fetchImpl ? fetchImpl(...args) : Promise.resolve({
        ok: true,
        json: () => Promise.resolve({
          event_id: id, expires: 1999999999, signature: "a".repeat(64)
        })
      });
    },
    crypto: crypto ? {getRandomValues(arr) {
      arr.forEach((_, i) => {arr[i] = i + 1;});
      return arr;
    }} : null,
  };
  const document = {cookie: "_fbp=fb.1.1795555555555.1234567890"};
  vm.runInNewContext(source, {window, document, Uint8Array, encodeURIComponent, Promise});
  return {window, pixels, requests, id};
}
async function settle() {
  for (let i = 0; i < 4; i++) await new Promise(resolve => setImmediate(resolve));
}

test("sem consentimento: não dispara Pixel nem CAPI", async () => {
  const t = setUp({consent: false});
  t.window.rbTrackViewContentWithCapi({content_name: "Produto"});
  await settle();
  assert.equal(t.pixels.length, 0);
  assert.equal(t.requests.length, 0);
});

test("relay não configurado: ViewContent permanece no Pixel", async () => {
  const t = setUp({configured: false});
  t.window.rbTrackViewContentWithCapi({content_name: "Produto"});
  await settle();
  assert.equal(t.pixels.length, 1);
  assert.equal(t.pixels[0][0], "track");
  assert.equal(t.pixels[0][1], "ViewContent");
  assert.equal(t.pixels[0][3].eventID, t.id);
  assert.equal(t.requests.length, 0);
});

test("o mesmo eventID é enviado ao Pixel e ao relay", async () => {
  const t = setUp();
  t.window.rbTrackViewContentWithCapi({content_name: "Produto"});
  await settle();
  assert.equal(t.requests.length, 2);
  assert.equal(t.pixels[0][3].eventID, t.id);
  assert.match(t.requests[0][0], /\/v1\/view-token\?event_id=rbvc-/);
  const post = JSON.parse(t.requests[1][1].body);
  assert.equal(post.event_id, t.id);
  assert.equal(post.consent, true);
  assert.equal(post.fbp, "fb.1.1795555555555.1234567890");
  assert.equal(post.email, undefined);
  assert.equal(post.phone, undefined);
});

test("se servidor falhar, medição do Pixel continua", async () => {
  const t = setUp({fetchImpl: () => Promise.reject(new Error("offline"))});
  t.window.rbTrackViewContentWithCapi({});
  await settle();
  assert.equal(t.pixels.length, 1);
  assert.equal(t.requests.length, 1);
});

test("consentimento revogado durante o fetch impede envio CAPI", async () => {
  let release;
  const t = setUp({fetchImpl: () => new Promise(resolve => { release = resolve; })});
  t.window.rbTrackViewContentWithCapi({});
  t.window.RB_META_CONSENT_GRANTED = false;
  release({ok: true, json: async () => ({
    event_id: t.id, expires: 1999999999, signature: "a".repeat(64)
  })});
  await settle();
  assert.equal(t.requests.length, 1);
});

test("sem Web Crypto, mantém ViewContent no Pixel sem CAPI", async () => {
  const t = setUp({crypto: false});
  t.window.rbTrackViewContentWithCapi({content_name: "Produto"});
  await settle();
  assert.equal(t.pixels.length, 1);
  assert.equal(t.pixels[0][3], undefined);
  assert.equal(t.requests.length, 0);
});
