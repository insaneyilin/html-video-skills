import fs from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { randomUUID } from "node:crypto";
import {
  projectRoot,
  current,
  htmlVideoRoot,
  inside,
  json,
  writeJson,
} from "./runtime.mjs";

const root = await fs.realpath(projectRoot());
const { project, timing, signature } = await current(root);
const composed = await json(path.join(root, "work/composed.json"));
if (composed.source_signature !== signature)
  throw new Error("HTML scenes are stale; compose again");
const engineRoot = htmlVideoRoot();
const {
  EngineRegistry,
  TemplateRegistry,
  ProjectStore,
  AssetStore,
  ProjectOrchestrator,
} = await import(
  pathToFileURL(path.join(engineRoot, "packages/core/dist/index.js"))
);
const { default: adapter } = await import(
  pathToFileURL(
    path.join(engineRoot, "packages/adapter-hyperframes/dist/index.js"),
  )
);
const engines = new EngineRegistry();
engines.register(adapter);
const projects = new ProjectStore(root);
const orchestrator = new ProjectOrchestrator({
  projectRoot: root,
  engines,
  templates: new TemplateRegistry(),
  projects,
  assets: new AssetStore({ projectRoot: root }),
});
const record = await orchestrator.create({
  name: project.title,
  intent: "Narrated product demonstration",
  preferences: {
    resolution: { width: timing.video.width, height: timing.video.height },
    fps: timing.video.fps,
    language: project.language,
    format: "mp4",
  },
});
await orchestrator.writeContentGraph(
  record.id,
  await json(path.join(root, "work/content-graph.json")),
);
for (const scene of timing.scenes)
  await orchestrator.writeFrameHtml(
    record.id,
    scene.id,
    await fs.readFile(
      path.join(root, "work/scenes", scene.id + ".html"),
      "utf8",
    ),
  );
const sound = await orchestrator.addFileAsset(
  record.id,
  await inside(root, timing.narration),
  "Local narration",
);
const audio = sound.assets.find((a) => a.metadata.filename === "narration.wav");
if (!audio) throw new Error("Narration asset was not registered");
sound.soundtrack = {
  narrationAssetId: audio.id,
  narrationVolumeDb: 0,
  narrationText: timing.scenes.flatMap((s) => s.narration).join("\n"),
  narrationByFrame: Object.fromEntries(
    timing.scenes.map((s) => [s.id, s.narration.join("\n")]),
  ),
};
await projects.save(sound);
const id =
  new Date().toISOString().replace(/[:.]/g, "-") +
  "-" +
  randomUUID().slice(0, 6);
const destination = path.join(root, "exports", id);
await fs.mkdir(destination, { recursive: true });
let last = -1;
await orchestrator.exportMp4({
  projectId: record.id,
  outputPath: path.join(destination, "video.mp4"),
  onProgress: (pct, stage) => {
    const bucket = Math.floor(pct / 10);
    if (bucket !== last) {
      last = bucket;
      console.log(`${Math.round(pct)}% ${stage}`);
    }
  },
});
for (const file of [
  "subtitles.srt",
  "subtitles.vtt",
  "timing.json",
  "boundaries.json",
])
  await fs.copyFile(
    path.join(root, "work", file),
    path.join(destination, file),
  );
await fs.copyFile(
  path.join(root, "project.json"),
  path.join(destination, "project.json"),
);
const report = {
  id,
  source_signature: signature,
  projectId: record.id,
  video: `exports/${id}/video.mp4`,
  directory: `exports/${id}`,
  planned_duration: timing.duration,
  voice: timing.voice,
  engine: "html-video / Hyperframes",
};
await writeJson(path.join(destination, "render.json"), report);
await writeJson(path.join(root, "work/candidate.json"), report);
console.log(
  `Rendered candidate: ${report.video}. Run verify.mjs --stage export before publishing the local preview.`,
);
