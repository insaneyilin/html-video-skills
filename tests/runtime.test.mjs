import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { previewServer } from "../skills/html-video-demo/scripts/serve.mjs";

test("preview serves ranges and keeps runtime state private", async (t) => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), "html-video-skill-"));
  await fs.mkdir(path.join(root, "exports"));
  await fs.mkdir(path.join(root, "work"));
  await fs.writeFile(path.join(root, "review.html"), "<h1>Example</h1>");
  await fs.writeFile(path.join(root, "exports/clip.mp4"), "0123456789");
  await fs.writeFile(path.join(root, "work/private.json"), "{}");
  const app = await previewServer(root);
  t.after(async () => {
    await app.close();
    await fs.rm(root, { recursive: true, force: true });
  });
  const partial = await fetch(app.url + "exports/clip.mp4", {
    headers: { Range: "bytes=2-5" },
  });
  assert.equal(partial.status, 206);
  assert.equal(await partial.text(), "2345");
  assert.equal(
    (
      await fetch(app.url + "exports/clip.mp4", {
        headers: { Range: "bytes=30-" },
      })
    ).status,
    416,
  );
  assert.equal((await fetch(app.url + "work/private.json")).status, 404);
  assert.equal((await fetch(app.url, { method: "POST" })).status, 405);
});
