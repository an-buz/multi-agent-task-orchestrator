import test from "node:test";
import assert from "node:assert/strict";
import { loadCatalogue } from "../src/lib/pagination.ts";
import { listRuns } from "../src/features/runs/api.ts";

for (const path of ["/agents", "/workflows"]) {
  test(`${path} catalogue follows all pages including a partial last page`, async (t) => {
    const source = Array.from({ length: 121 }, (_, id) => ({ id: String(id) }));
    const offsets = [];
    const controller = new AbortController();
    t.mock.method(globalThis, "fetch", async (url, init) => {
      const parsed = new URL(url);
      assert.equal(parsed.pathname, `/api/v1${path}`);
      assert.equal(init.signal, controller.signal);
      const offset = Number(parsed.searchParams.get("offset"));
      const limit = Number(parsed.searchParams.get("limit"));
      assert.equal(limit, 50);
      offsets.push(offset);
      return Response.json({ items: source.slice(offset, offset + limit), total: source.length });
    });
    assert.deepEqual(await loadCatalogue(path, controller.signal), { items: source, total: 121 });
    assert.deepEqual(offsets, [0, 50, 100]);
  });
}

test("catalogue does not return partial data on page failure or loop on an inconsistent total", async (t) => {
  let calls = 0;
  t.mock.method(globalThis, "fetch", async () => {
    calls++;
    return Response.json({ items: calls === 1 ? [{ id: "1" }] : [], total: 2 });
  });
  await assert.rejects(loadCatalogue("/agents"), /changed while loading/);
  assert.equal(calls, 2);
  t.mock.method(globalThis, "fetch", async () => new Response(null, { status: 500 }));
  await assert.rejects(loadCatalogue("/agents"), /500/);
});

test("run history requests a bounded page and preserves cancellation", async (t) => {
  const controller = new AbortController();
  t.mock.method(globalThis, "fetch", async (url, init) => {
    assert.match(url, /\/runs\?limit=50&offset=100$/);
    assert.equal(init.signal, controller.signal);
    return Response.json({ items: [], total: 100 });
  });
  assert.deepEqual(await listRuns(controller.signal, 100), { items: [], total: 100 });
});
