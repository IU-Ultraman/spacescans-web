// The /api/datasets client and the task config (src/lib/api.ts) against a
// mocked fetch and a fake XMLHttpRequest. No server, synthetic values only.
import test, { beforeEach } from "node:test";
import assert from "node:assert/strict";

process.env.NEXT_PUBLIC_API_URL = "http://api.test";
const { api, ApiError, describeError } = await import("../.next-check/lib/api.js");

const BASE = "http://api.test";
let calls = [];
let replies = [];

/** Queue the next fetch reply. */
function reply(status, body) {
  replies.push({ status, body });
}

globalThis.fetch = async (url, init = {}) => {
  calls.push({ url, init });
  const next = replies.shift();
  assert.ok(next, `unexpected fetch ${init.method ?? "GET"} ${url}`);
  const text = next.body === undefined ? null : typeof next.body === "string" ? next.body : JSON.stringify(next.body);
  return new Response(text, { status: next.status, headers: { "Content-Type": "application/json" } });
};

class FakeXHR {
  static next = null;
  static last = null;
  constructor() {
    this.headers = {};
    this.upload = {};
    FakeXHR.last = this;
  }
  open(method, url) {
    this.method = method;
    this.url = url;
  }
  setRequestHeader(k, v) {
    this.headers[k] = v;
  }
  send(body) {
    this.body = body;
    const { status, body: resp } = FakeXHR.next;
    queueMicrotask(() => {
      this.upload.onprogress?.({ lengthComputable: true, loaded: 50, total: 100 });
      this.status = status;
      this.responseText = resp === undefined ? "" : typeof resp === "string" ? resp : JSON.stringify(resp);
      this.onload?.();
    });
  }
}
globalThis.XMLHttpRequest = FakeXHR;

beforeEach(() => {
  calls = [];
  replies = [];
  FakeXHR.next = null;
  FakeXHR.last = null;
});

const dataset = (over = {}) => ({
  id: "0123456789abcdef0123456789abcdef",
  name: "Greenness",
  kind: "polygon_table",
  temporal: "yearly",
  variables: [{ name: "ndvi", unit: "index" }],
  visibility: "private",
  owned_by_me: true,
  owner_display: "you",
  created_at: "2026-10-16T12:00:00Z",
  status: "ready",
  ...over,
});

test("list: a bare array or an envelope", async () => {
  reply(200, [dataset(), dataset({ id: "ff", owned_by_me: false, visibility: "deployment" })]);
  const list = await api.listDatasets();
  assert.equal(calls[0].url, `${BASE}/api/datasets`);
  assert.equal(calls[0].init.method, undefined); // GET
  assert.equal(list.length, 2);
  assert.equal(list[1].visibility, "deployment");

  reply(200, { datasets: [dataset()] });
  assert.equal((await api.listDatasets()).length, 1);
});

test("get: unwraps {dataset}", async () => {
  reply(200, { dataset: dataset({ source: "Lab" }) });
  const d = await api.getDataset("0123456789abcdef0123456789abcdef");
  assert.equal(calls[0].url, `${BASE}/api/datasets/0123456789abcdef0123456789abcdef`);
  assert.equal(d.source, "Lab");
});

test("create: multipart with repeated files parts and a metadata JSON part", async () => {
  FakeXHR.next = { status: 201, body: { dataset: dataset() } };
  const metadata = {
    name: "Greenness",
    kind: "raster",
    temporal: "yearly",
    variables: [{ name: "ndvi", band: 1 }],
    periods: [{ file: "a_2014.tif", year: 2014 }, { file: "a_2015.tif", year: 2015 }],
    visibility: "private",
  };
  const files = [new File(["x"], "a_2014.tif"), new File(["y"], "a_2015.tif")];
  const progress = [];
  const created = await api.createDataset({ files, metadata }, (p) => progress.push(p));
  const xhr = FakeXHR.last;
  assert.equal(xhr.method, "POST");
  assert.equal(xhr.url, `${BASE}/api/datasets`);
  assert.equal(xhr.headers["Content-Type"], undefined); // the browser sets the boundary
  const parts = [...xhr.body.entries()];
  assert.deepEqual(parts.map(([k]) => k), ["files", "files", "metadata"]);
  assert.deepEqual(parts.slice(0, 2).map(([, v]) => v.name), ["a_2014.tif", "a_2015.tif"]);
  assert.deepEqual(JSON.parse(parts[2][1]), metadata);
  assert.deepEqual(progress, [50]);
  assert.equal(created.id, dataset().id);
});

test("create: a reply that does not describe the dataset resolves to null", async () => {
  FakeXHR.next = { status: 201, body: { status: "ok" } };
  assert.equal(await api.createDataset({ files: [], metadata: {} }), null);
});

test("create: validation errors carry the issues, top-level or nested in FastAPI's detail", async () => {
  const issues = ["key column: 3 of 10 codes are not 11-digit tract codes", { field: "variables", message: "ndvi is not numeric" }];
  for (const body of [
    { detail: "The dataset was not accepted", issues },
    { detail: { detail: "The dataset was not accepted", issues } },
  ]) {
    FakeXHR.next = { status: 400, body };
    await assert.rejects(api.createDataset({ files: [], metadata: {} }), (err) => {
      assert.ok(err instanceof ApiError);
      assert.equal(err.status, 400);
      assert.equal(err.message, "The dataset was not accepted");
      assert.deepEqual(err.issues, [
        "key column: 3 of 10 codes are not 11-digit tract codes",
        "variables: ndvi is not numeric",
      ]);
      return true;
    });
  }
  FakeXHR.next = { status: 413, body: undefined };
  await assert.rejects(api.createDataset({ files: [], metadata: {} }), /larger than this server accepts/);
});

test("update: PATCH with only the given fields", async () => {
  reply(200, dataset({ visibility: "deployment" }));
  const d = await api.updateDataset("abc", { visibility: "deployment" });
  assert.equal(calls[0].url, `${BASE}/api/datasets/abc`);
  assert.equal(calls[0].init.method, "PATCH");
  assert.deepEqual(JSON.parse(calls[0].init.body), { visibility: "deployment" });
  assert.equal(d.visibility, "deployment");

  reply(200, { status: "updated" });
  assert.equal(await api.updateDataset("abc", { name: "x" }), null);

  reply(403, { detail: "Only the owner can change this dataset" });
  await assert.rejects(api.updateDataset("abc", { name: "x" }), (err) => err.status === 403 && /owner/.test(err.message));
});

test("delete: 204 without a body is fine; 409 explains why", async () => {
  reply(204, undefined);
  assert.equal(await api.deleteDataset("abc"), null);
  assert.equal(calls[0].init.method, "DELETE");

  reply(409, { detail: "A running task uses this dataset" });
  await assert.rejects(api.deleteDataset("abc"), (err) => err.status === 409 && /running task/.test(err.message));
});

test("task config: output level and dataset ids go next to the catalog variables", async () => {
  reply(200, { status: "saved" });
  await api.saveConfig("t1", {
    buffer: { size: 270, raster_res_m: 25 },
    variables: ["ndi"],
    output_level: "participant",
    custom_datasets: ["abc"],
  });
  assert.equal(calls[0].url, `${BASE}/api/tasks/t1/config`);
  assert.equal(calls[0].init.method, "PUT");
  assert.deepEqual(JSON.parse(calls[0].init.body), {
    experiment: "auto",
    buffer: { size: 270, raster_res_m: 25 },
    variables: ["ndi"],
    output_level: "participant",
    custom_datasets: ["abc"],
  });
});

test("error bodies never surface as [object Object]", () => {
  assert.deepEqual(describeError({ detail: [{ loc: ["body", "metadata"], msg: "field required" }] }, "x"), {
    message: "metadata: field required",
    issues: [],
  });
  assert.deepEqual(
    describeError({ detail: [{ loc: ["body", "a"], msg: "bad" }, { loc: ["body", "b"], msg: "worse" }] }, "x"),
    { message: "Please correct the following:", issues: ["a: bad", "b: worse"] },
  );
  assert.deepEqual(describeError({ detail: { error: "no_boundary", message: "No boundary data" } }, "x"), {
    message: "No boundary data",
    issues: [],
  });
  assert.deepEqual(describeError("plain text", "x"), { message: "plain text", issues: [] });
  assert.deepEqual(describeError({}, "fallback"), { message: "fallback", issues: [] });
  assert.deepEqual(describeError(null, "fallback"), { message: "fallback", issues: [] });
});
