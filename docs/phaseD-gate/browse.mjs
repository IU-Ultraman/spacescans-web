// Headless Chrome over the DevTools protocol against the TEST stack (I2), adapted from
// track D's drive.mjs. usage:
//   node --experimental-websocket browse.mjs <outdir> <base> <tokenB> <tokenA> <taskP> <taskE> <datadir> <api>
import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

const [OUT, BASE, TOKEN_B, TOKEN_A, TASK_P, TASK_E, DATA, API] = process.argv.slice(2);
const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const PORT = 9231;
fs.mkdirSync(path.join(OUT, "shots"), { recursive: true });
const chrome = spawn(CHROME, ["--headless=new", `--remote-debugging-port=${PORT}`,
  `--user-data-dir=${path.join(OUT, "profile")}`, "--no-first-run", "--no-default-browser-check",
  "--disable-extensions", "--window-size=1400,1000", "about:blank"], { stdio: "ignore" });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const steps = [];
const note = (s) => { steps.push(s); console.log(s); };
async function pageWs() {
  for (let i = 0; i < 100; i++) {
    try {
      const list = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json();
      const page = list.find((t) => t.type === "page");
      if (page) return page.webSocketDebuggerUrl;
    } catch {}
    await sleep(200);
  }
  throw new Error("no Chrome page target");
}
const ws = new WebSocket(await pageWs());
await new Promise((r) => (ws.onopen = r));
let nextId = 0;
const pending = new Map();
const events = [];
function send(method, params = {}) {
  const id = ++nextId;
  ws.send(JSON.stringify({ id, method, params }));
  return new Promise((resolve, reject) => pending.set(id, { resolve, reject }));
}
ws.onmessage = (ev) => {
  const msg = JSON.parse(ev.data);
  if (msg.id && pending.has(msg.id)) {
    const { resolve, reject } = pending.get(msg.id);
    pending.delete(msg.id);
    msg.error ? reject(new Error(msg.error.message)) : resolve(msg.result);
  } else if (msg.method) {
    if (msg.method === "Page.javascriptDialogOpening") send("Page.handleJavaScriptDialog", { accept: true });
    events.push(msg);
  }
};
await send("Page.enable"); await send("Runtime.enable"); await send("Log.enable"); await send("DOM.enable");
await send("Emulation.setDeviceMetricsOverride", { width: 1400, height: 1000, deviceScaleFactor: 1, mobile: false });
async function evaluate(expression) {
  const r = await send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
  if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description ?? r.exceptionDetails.text);
  return r.result.value;
}
async function waitFor(expr, label, timeout = 45000) {
  const t0 = Date.now();
  while (Date.now() - t0 < timeout) {
    try { if (await evaluate(expr)) { note(`ok: ${label}`); return; } } catch {}
    await sleep(250);
  }
  throw new Error(`timeout: ${label}`);
}
const hasText = (t) =>
  `!!document.body && document.body.innerText.toLowerCase().includes(${JSON.stringify(t.toLowerCase())})`;
async function nav(url) {
  await send("Page.navigate", { url });
  await sleep(300);
  await waitFor("document.readyState === 'complete'", `load ${url.replace(BASE, "")}`);
}
async function shot(name) {
  await sleep(600);
  const m = await send("Page.getLayoutMetrics");
  const r = await send("Page.captureScreenshot", { format: "png", captureBeyondViewport: true,
    clip: { x: 0, y: 0, width: Math.ceil(m.cssContentSize.width),
            height: Math.min(Math.ceil(m.cssContentSize.height), 5000), scale: 1 } });
  fs.writeFileSync(path.join(OUT, "shots", `${name}.png`), Buffer.from(r.data, "base64"));
  note(`shot ${name}`);
}

async function click(selector, text = "") {
  const ok = await evaluate(`(() => {
    const els = [...document.querySelectorAll(${JSON.stringify(selector)})];
    const el = els.find((e) => (e.innerText || e.getAttribute("aria-label") || "").includes(${JSON.stringify(text)}));
    if (!el) return false;
    el.scrollIntoView({ block: "center" });
    el.click();
    return true;
  })()`);
  if (!ok) throw new Error(`no ${selector} with "${text}"`);
  await sleep(250);
}
async function fill(selector, value, index = 0) {
  const ok = await evaluate(`(() => {
    const el = document.querySelectorAll(${JSON.stringify(selector)})[${index}];
    if (!el) return false;
    const proto = el.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto, "value").set.call(el, ${JSON.stringify(value)});
    el.dispatchEvent(new Event("input", { bubbles: true }));
    return true;
  })()`);
  if (!ok) throw new Error(`no input ${selector}`);
  await sleep(200);
}
async function setFiles(selector, files) {
  const doc = await send("DOM.getDocument", { depth: -1, pierce: true });
  const q = await send("DOM.querySelector", { nodeId: doc.root.nodeId, selector });
  if (!q.nodeId) throw new Error(`no ${selector}`);
  await send("DOM.setFileInputFiles", { nodeId: q.nodeId, files });
  await sleep(800);
}
const NAME_INPUT = '[data-slot=dialog-content] input[placeholder="e.g. Neighborhood greenness"]';
async function signIn(token, email) {
  await nav(`${BASE}/login`);
  await evaluate(`localStorage.setItem("token", ${JSON.stringify(token)}); localStorage.setItem("email", ${JSON.stringify(email)}); true`);
}
let failed = null;
try {
  await signIn(TOKEN_B, "ben.tester@example.com");
  await nav(`${BASE}/dashboard`);
  await waitFor(hasText("e2e participant level") + " && " + hasText("e2e episode level"), "B's task list");
  await shot("01-dashboard-B");
  await nav(`${BASE}/dashboard/datasets`);
  await waitFor(hasText("Synthetic daily tract values") + " && " + hasText("Synthetic biweekly raster")
    + " && " + hasText("Synthetic sites") + " && " + hasText("Shared by Ada Tester"), "B sees A's 3 shared datasets");
  await waitFor(`!(${hasText("Synthetic private table")})`, "B does not see A's private dataset");
  await shot("02-datasets-B");
  await nav(`${BASE}/dashboard/task/${TASK_P}/results`);
  await waitFor(hasText("Result Preview") + " && " + hasText("syn_daily") + " && " + hasText("participant"),
    "participant results page");
  await sleep(1500);
  await shot("03-results-participant");
  await nav(`${BASE}/dashboard/task/${TASK_E}/results`);
  await waitFor(hasText("Result Preview") + " && " + hasText("syn_daily") + " && " + hasText("episode"),
    "episode results page");
  await sleep(1500);
  await shot("04-results-episode");
  await nav(`${BASE}/dashboard/task/new`);
  await waitFor(hasText("upload"), "new-task wizard");
  await shot("05-wizard");
  await signIn(TOKEN_A, "ada.tester@example.com");
  await nav(`${BASE}/dashboard/datasets`);
  await waitFor(hasText("Synthetic sites") + " && " + hasText("you are responsible for making sure the source"),
    "owner A sees the share control with the warning");
  await shot("06-datasets-A-share-warning");

  // UI uploads against the real backend (private, so B's view stays as it is)
  const bw = fs.readdirSync(path.join(DATA, "bw")).filter((f) => f.endsWith(".tif")).sort()
    .map((f) => path.join(DATA, "bw", f));
  await click("button", "Add dataset");
  await waitFor(hasText("Add a dataset"), "upload dialog (daily table)");
  await click("[data-slot=dialog-content] button", "Daily");
  await setFiles("#dataset-csv", [path.join(DATA, "daily_tract.csv")]);
  await waitFor(hasText("Which column is which?"), "column mapping read from the CSV header");
  await click("[data-slot=dialog-content] label", "syn_daily");
  await fill(NAME_INPUT, "UI daily table");
  await shot("07-ui-upload-daily-table");
  await click("[data-slot=dialog-footer] button", "Add dataset");
  await waitFor(`!(${hasText("Add a dataset")}) && ${hasText("UI daily table")}`, "UI daily table registered", 120000);

  await click("button", "Add dataset");
  await waitFor(hasText("Add a dataset"), "upload dialog (raster)");
  await click("[data-slot=dialog-content] button", "Raster (GeoTIFF)");
  await click("[data-slot=dialog-content] button", "Biweekly");
  await setFiles("#dataset-rasters", bw);
  await waitFor(`document.querySelectorAll('[data-slot=dialog-content] table tbody tr').length === ${bw.length}`,
    "one period row per GeoTIFF, read from the file names");
  await fill('input[aria-label="Result column of band row 1"]', "ui_bw");
  await fill(NAME_INPUT, "UI biweekly raster");
  await shot("08-ui-upload-biweekly-raster");
  await click("[data-slot=dialog-footer] button", "Add dataset");
  await waitFor(`!(${hasText("Add a dataset")}) && ${hasText("UI biweekly raster")}`, "UI biweekly raster registered", 120000);

  await click("button", "Add dataset");
  await waitFor(hasText("Add a dataset"), "upload dialog (features)");
  await click("[data-slot=dialog-content] button", "Features (points, lines or polygons)");
  await setFiles("#dataset-features", [path.join(DATA, "sites.gpkg")]);
  await fill(NAME_INPUT, "UI sites");
  await shot("09-ui-upload-features");
  await click("[data-slot=dialog-footer] button", "Add dataset");
  await waitFor(`!(${hasText("Add a dataset")}) && ${hasText("UI sites")}`, "UI sites registered", 120000);
  await shot("10-datasets-A-after-ui-uploads");

  const list = await (await fetch(`${API}/api/datasets`, { headers: { Authorization: `Bearer ${TOKEN_A}` } })).json();
  const want = { "UI daily table": ["polygon_table", "daily", "syn_daily"],
                 "UI biweekly raster": ["raster", "biweekly", "ui_bw"],
                 "UI sites": ["features", "static", "ui_sites_dist_m"] };
  for (const [name, [kind, temporal, col]] of Object.entries(want)) {
    const d = list.find((x) => x.name === name);
    const ok = d && d.kind === kind && d.temporal === temporal && d.status === "ready"
      && d.visibility === "private" && d.variables.map((v) => v.name).join() === col;
    if (!ok) throw new Error(`UI upload ${name} not registered as expected: ${JSON.stringify(d)}`);
    note(`ok: API record of ${name} (${kind}/${temporal}, private, ready, column ${col})`);
  }
} catch (e) {
  failed = String(e && e.stack ? e.stack : e);
  console.log("FAILED:", failed);
  try { await shot("zz-failure"); } catch {}
}
const problems = events.filter((e) => e.method === "Runtime.exceptionThrown"
    || (e.method === "Runtime.consoleAPICalled" && ["error", "assert"].includes(e.params.type))
    || (e.method === "Log.entryAdded" && e.params.entry.level === "error"))
  .map((e) => e.method === "Runtime.exceptionThrown"
    ? { kind: "exception", text: e.params.exceptionDetails.exception?.description ?? e.params.exceptionDetails.text }
    : e.method === "Runtime.consoleAPICalled"
      ? { kind: "console.error", text: e.params.args.map((a) => a.value ?? a.description ?? "").join(" ") }
      : { kind: "log", text: `${e.params.entry.text} ${e.params.entry.url ?? ""}` });
fs.writeFileSync(path.join(OUT, "report.json"), JSON.stringify({ failed, steps, problems }, null, 2));
console.log(`problems: ${problems.length}`);
ws.close();
chrome.kill("SIGTERM");
process.exit(failed ? 1 : 0);
