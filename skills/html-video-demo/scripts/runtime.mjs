import fs from "node:fs/promises";
import path from "node:path";
import { createHash } from "node:crypto";
import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";
import { spawn } from "node:child_process";

export function option(name, fallback) {
  const index = process.argv.indexOf(name);
  if (index < 0) return fallback;
  const value = process.argv[index + 1];
  if (!value || value.startsWith("--"))
    throw new Error(`Missing ${name} value`);
  return value;
}
export function projectRoot() {
  const root = option("--project");
  if (!root) throw new Error("--project is required");
  return path.resolve(root);
}
export async function json(file) {
  return JSON.parse(await fs.readFile(file, "utf8"));
}
export async function writeJson(file, value) {
  await fs.mkdir(path.dirname(file), { recursive: true });
  await fs.writeFile(file, JSON.stringify(value, null, 2) + "\n");
}
export async function inside(root, relative, mustExist = true) {
  if (
    typeof relative !== "string" ||
    !relative ||
    path.isAbsolute(relative) ||
    relative.includes("\\")
  )
    throw new Error("Expected a project-relative path");
  const full = path.resolve(root, relative),
    canonicalRoot = await fs.realpath(root);
  const lexical = path.relative(canonicalRoot, full);
  if (lexical.startsWith("..") || path.isAbsolute(lexical))
    throw new Error("Path leaves the project");
  const resolved = mustExist ? await fs.realpath(full) : full;
  const relation = path.relative(canonicalRoot, resolved);
  if (relation.startsWith("..") || path.isAbsolute(relation))
    throw new Error("Symlink leaves the project");
  return resolved;
}
export async function current(root) {
  const bytes = await fs.readFile(path.join(root, "project.json"));
  const project = JSON.parse(bytes),
    signature = createHash("sha256").update(bytes).digest("hex");
  const timing = await json(path.join(root, "work/timing.json"));
  if (timing.source_signature !== signature)
    throw new Error(
      "Timing is stale; run the audio stages for the current project.json",
    );
  return { project, timing, signature };
}
export function htmlVideoRoot() {
  const root = option("--html-video", process.env.HTML_VIDEO_ROOT);
  if (!root) throw new Error("Provide --html-video or HTML_VIDEO_ROOT");
  return path.resolve(root);
}
export async function playwright() {
  const root = htmlVideoRoot();
  const require = createRequire(
    path.join(root, "packages/adapter-hyperframes/package.json"),
  );
  const module = await import(pathToFileURL(require.resolve("playwright")));
  return module.chromium ? module : module.default;
}
export function run(command, args) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { stdio: ["ignore", "pipe", "pipe"] });
    const chunks = [];
    let stderr = "";
    child.stdout.on("data", (c) => chunks.push(c));
    child.stderr.on("data", (c) => (stderr += c));
    child.on("error", reject);
    child.on("close", (code) =>
      code === 0
        ? resolve({ stdout: Buffer.concat(chunks), stderr })
        : reject(new Error(`${command}: ${stderr.slice(-2000)}`)),
    );
  });
}
export const escapeHtml = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
export const scriptJson = (value) =>
  JSON.stringify(value).replaceAll("<", "\\u003c");
