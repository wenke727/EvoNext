import assert from "node:assert/strict";
import { test } from "node:test";
import { MediaCache } from "../src/evidence/media.ts";
const tick = () => new Promise((resolve) => setImmediate(resolve));

// These tests exercise network ownership and cache isolation, not presentation markup.
test("same snapshot/path shares a request; snapshots never share media identity", async () => {
  const calls = [];
  const cache = new MediaCache(async (snapshot, path) => {
    calls.push([snapshot, path]);
    return new Blob([snapshot]);
  });
  const a = cache.acquire("first", "same.png");
  const b = cache.acquire("first", "same.png");
  const c = cache.acquire("second", "same.png");
  assert.equal(await (await a.promise).text(), "first");
  assert.equal(await b.promise, await a.promise);
  assert.equal(await (await c.promise).text(), "second");
  assert.equal(calls.length, 2);
  a.release();
  b.release();
  c.release();
  cache.dispose();
});

test("caps active reads and drops queued reads when the final consumer leaves", async () => {
  const running = [];
  const cache = new MediaCache(
    (snapshot, path, signal) =>
      new Promise((resolve, reject) => {
        running.push({ path, resolve });
        signal.addEventListener("abort", () =>
          reject(new DOMException("Aborted", "AbortError")),
        );
      }),
    1,
  );
  const a = cache.acquire("s", "a");
  const b = cache.acquire("s", "b");
  const rejected = assert.rejects(b.promise, { name: "AbortError" });
  await tick();
  assert.equal(running.length, 1);
  b.release();
  await rejected;
  running[0].resolve(new Blob(["a"]));
  await a.promise;
  await tick();
  assert.equal(running.length, 1);
  a.release();
  cache.dispose();
});

test("one consumer leaving does not cancel another consumer; the last one cancels", async () => {
  let signal;
  const cache = new MediaCache((_snapshot, _path, value) => {
    signal = value;
    return new Promise(() => {});
  });
  const a = cache.acquire("s", "a");
  const b = cache.acquire("s", "a");
  const rejected = assert.rejects(a.promise, { name: "AbortError" });
  await tick();
  a.release();
  assert.equal(signal.aborted, false);
  b.release();
  assert.equal(signal.aborted, true);
  await rejected;
  cache.dispose();
});

test("failed reads can retry and released blobs are evicted when the byte budget is exceeded", async () => {
  let calls = 0;
  const cache = new MediaCache(
    async () => {
      calls++;
      if (calls === 1) throw new Error("network");
      return new Blob(["1234"]);
    },
    4,
    3,
  );
  const first = cache.acquire("s", "a");
  await assert.rejects(first.promise, /network/);
  first.release();
  const retry = cache.acquire("s", "a");
  await retry.promise;
  retry.release();
  const again = cache.acquire("s", "a");
  await again.promise;
  assert.equal(calls, 3);
  again.release();
  cache.dispose();
});

test("closing a credential session aborts all requests and prevents reuse", async () => {
  let signal;
  const cache = new MediaCache((_snapshot, _path, value) => {
    signal = value;
    return new Promise(() => {});
  });
  const lease = cache.acquire("s", "a");
  const rejected = assert.rejects(lease.promise, { name: "AbortError" });
  await tick();
  cache.dispose();
  await rejected;
  assert.equal(signal.aborted, true);
  assert.throws(() => cache.acquire("s", "a"), /closed/);
  lease.release();
});
