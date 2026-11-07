import http from "node:http";
import fs from "node:fs/promises";
import { createReadStream } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { projectRoot, option } from "./runtime.mjs";

const types = {
  ".html": "text/html; charset=utf-8",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".svg": "image/svg+xml",
  ".mp4": "video/mp4",
  ".webm": "video/webm",
  ".wav": "audio/wav",
  ".mp3": "audio/mpeg",
  ".srt": "text/plain; charset=utf-8",
  ".vtt": "text/vtt; charset=utf-8",
  ".json": "application/json; charset=utf-8",
};
export async function previewServer(root, port = 0) {
  root = await fs.realpath(root);
  const server = http.createServer(async (req, res) => {
    try {
      if (!["GET", "HEAD"].includes(req.method)) {
        res.writeHead(405);
        res.end();
        return;
      }
      const requestPath = decodeURIComponent(
        new URL(req.url, "http://localhost").pathname,
      );
      const relative =
        requestPath === "/" ? "review.html" : requestPath.slice(1);
      const parts = relative.split("/");
      if (
        parts.some((p) => p.startsWith(".")) ||
        relative.includes("\\") ||
        !(
          relative === "review.html" || ["assets", "exports"].includes(parts[0])
        )
      )
        throw new Error("Not public");
      const file = await fs.realpath(path.join(root, relative));
      if (!file.startsWith(root + path.sep)) throw new Error("Path escape");
      const stat = await fs.stat(file);
      if (!stat.isFile()) throw new Error("Not a file");
      const headers = {
        "Content-Type": types[path.extname(file)] || "application/octet-stream",
        "Cache-Control": "no-store",
        "Accept-Ranges": "bytes",
      };
      let start = 0,
        end = stat.size - 1,
        status = 200;
      if (req.headers.range) {
        const match = req.headers.range.match(/^bytes=(\d+)-(\d*)$/);
        if (
          !match ||
          Number(match[1]) >= stat.size ||
          (match[2] && Number(match[2]) < Number(match[1]))
        ) {
          res.writeHead(416, { "Content-Range": `bytes */${stat.size}` });
          res.end();
          return;
        }
        start = Number(match[1]);
        end = match[2] ? Math.min(Number(match[2]), end) : end;
        status = 206;
        headers["Content-Range"] = `bytes ${start}-${end}/${stat.size}`;
      }
      res.writeHead(status, { ...headers, "Content-Length": end - start + 1 });
      if (req.method === "HEAD") res.end();
      else createReadStream(file, { start, end }).pipe(res);
    } catch {
      res.writeHead(404);
      res.end("Not found");
    }
  });
  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(port, "127.0.0.1", resolve);
  });
  return {
    server,
    url: `http://127.0.0.1:${server.address().port}/`,
    close: () => new Promise((resolve) => server.close(resolve)),
  };
}
if (
  process.argv[1] &&
  path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)
) {
  const app = await previewServer(projectRoot(), Number(option("--port", 0)));
  console.log(`Local review: ${app.url}`);
  for (const signal of ["SIGINT", "SIGTERM"])
    process.once(signal, () => app.close().then(() => process.exit(0)));
}
