const test=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const vm=require("node:vm");
const path=require("node:path");
const code=fs.readFileSync(path.join(__dirname,"../checkout-attribution.js"),"utf8");
const html=fs.readFileSync(path.join(__dirname,"../index.html"),"utf8");

function setup(search,links) {
  const anchors=links.map(href=>({
    href,
    getAttribute(name){return name==="href"?href:null;}
  }));
  const window={location:{search}};
  const document={readyState:"complete",querySelectorAll:()=>anchors};
  vm.runInNewContext(code,{window,document,URL,URLSearchParams,Array});
  return {anchors,attribution:window.RBCheckoutAttribution};
}
test("script included, existing checkout offer preserved",()=>{
  assert.match(html,/checkout-attribution\.js/);
  assert.match(html,/href="https:\/\/pay\.hotmart\.com\/D108002435X"/);
});
test("paid traffic UTMs and SCK reach Hotmart",()=>{
  const input="?utm_source=instagram&utm_medium=paid_social&utm_campaign=rb7-vendas&utm_content=video01&utm_term=adset01";
  const r=setup(input,["https://pay.hotmart.com/D108002435X"]);
  const u=new URL(r.anchors[0].href);
  for (const [key,value] of Object.entries({utm_source:"instagram",utm_medium:"paid_social",utm_campaign:"rb7-vendas",utm_content:"video01",utm_term:"adset01"}))
    assert.equal(u.searchParams.get(key),value);
  assert.equal(u.searchParams.get("sck"),"r7-instagram-paid-social");
});
test("link without UTM receives only origin SCK, no invented Instagram data",()=>{
  const r=setup("",["https://pay.hotmart.com/D108002435X"]);
  const u=new URL(r.anchors[0].href);
  assert.equal(u.searchParams.get("sck"),"r7-landing");
  assert.equal(u.searchParams.has("utm_source"),false);
});
test("preserve split=1, coupons, existing UTMs and SCK",()=>{
  const original="https://pay.hotmart.com/D108002435X?split=1&off=ABCD&utm_source=facebook&sck=original";
  const r=setup("?utm_source=instagram&utm_campaign=rb7-vendas",[original]);
  const u=new URL(r.anchors[0].href);
  assert.equal(u.searchParams.get("split"),"1");
  assert.equal(u.searchParams.get("off"),"ABCD");
  assert.equal(u.searchParams.get("utm_source"),"facebook");
  assert.equal(u.searchParams.get("sck"),"original");
  assert.equal(u.searchParams.get("utm_campaign"),"rb7-vendas");
});
test("unrelated links are not changed",()=>{
  const originals=["#oferta","https://pay.hotmart.com/OTHER","https://example.com/"];
  const r=setup("?utm_source=instagram",originals);
  assert.deepEqual(r.anchors.map(x=>x.href),originals);
});
test("ignore invalid campaigns containing email and unsafe query",()=>{
  const r=setup("?utm_source=alex%40example.com&utm_campaign=%3Cscript%3E&fbclid=secret",["https://pay.hotmart.com/D108002435X"]);
  const u=new URL(r.anchors[0].href);
  assert.equal(u.searchParams.get("utm_source"),null);
  assert.equal(u.searchParams.get("utm_campaign"),null);
  assert.equal(u.searchParams.get("fbclid"),null);
});
