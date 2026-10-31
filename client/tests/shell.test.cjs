const test = require("node:test");
const assert = require("node:assert/strict");
const {serverURL, createShell, MAX_ROWS} = require("../app.js");

test("server URL uses host, IPv6, TLS and explicit override", () => {
  assert.equal(serverURL({hostname:"classroom", protocol:"http:", search:""}), "ws://classroom:8765/");
  assert.equal(serverURL({hostname:"::1", protocol:"https:", search:""}), "wss://[::1]:8765/");
  assert.equal(serverURL({hostname:"ignored", search:"?server=ws%3A%2F%2Fother%3A9000"}), "ws://other:9000/");
  assert.throws(() => serverURL({search:"?server=https://bad"}));
  assert.throws(() => serverURL({search:"?server=ws://user:pass@host"}));
});

// Minimal DOM contract: exercise paint scheduling and node bounds without a browser dependency.
class Element {
  constructor() { this.children=[]; this.dataset={}; this.listeners={}; this.scrollTop=0; this.clientHeight=100; this.textContent=""; }
  get scrollHeight() { return this.children.length * 20; }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children=children.flatMap(c => c.fragment ? c.children : [c]); }
  replaceWith() {}
  addEventListener(type, fn) { this.listeners[type]=fn; }
  setAttribute() {}
}
test("bursts paint once with Don’s store, preserve resume and bound DOM", async () => {
  const elements = Object.fromEntries(["live","recall","status","last-update","follow-live"].map(k => [k,new Element()]));
  const doc = {getElementById:k=>elements[k], querySelectorAll:()=>[], createElement:()=>new Element(),
    createDocumentFragment:()=>Object.assign(new Element(),{fragment:true}), createTextNode:text=>({textContent:text})};
  let callbacks=[], transport, closed=false, online=true;
  const {CaptionStore} = await import("../store.js");
  const store = new CaptionStore();
  const {createHistory} = await import("../history.js");
  const history = createHistory({now:()=>100});
  const shell=createShell({document:doc, store, history, url:"ws://local", clientId:1,
    isOnline:()=>online, createConnection:opts=>{transport=opts; return {close(){closed=true;}};},
    requestAnimationFrame:fn=>callbacks.push(fn), setInterval:()=>1, clearInterval:()=>{}, now:()=>100000});
  for(let i=1;i<=1000;i++) transport.onMessage({type:"CAPTION_UPDATE",segment:i,revision:1,final:true,text:"<b>text</b>",source_ts:99});
  assert.equal(callbacks.length,1);
  callbacks.shift()();
  assert.equal(elements.live.children.length,MAX_ROWS);
  assert.equal(elements.recall.children.length,MAX_ROWS);
  assert.equal(history.size,512);
  assert.deepEqual(transport.getResumeState(),{segment:1000,revision:1});
  transport.onStatus("connected"); assert.equal(elements.status.textContent,"Connected");
  online=false; transport.onStatus("reconnecting"); assert.equal(elements.status.textContent,"Offline"); assert.equal(elements.status.dataset.state,"closed");
  online=true; transport.onStatus("connected");
  elements.live.scrollTop=0; elements.live.listeners.scroll();
  assert.equal(elements["follow-live"].hidden,false);
  transport.onMessage({type:"CAPTION_UPDATE",segment:1001,revision:1,final:true,text:"next",source_ts:99});
  callbacks.shift()();
  assert.equal(elements.live.scrollTop,0);
  elements["follow-live"].listeners.click(); callbacks.shift()();
  assert.equal(elements.live.scrollTop,elements.live.scrollHeight);
  transport.onMessage({type:"HISTORY",items:[{segment:1002,revision:1,final:true,text:"recovered",source_ts:99}]});
  callbacks.shift()();
  assert.match(elements.recall.children.at(-1).className,/recovered/);
  shell.close(); assert.equal(closed,true);
});
