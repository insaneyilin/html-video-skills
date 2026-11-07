import fs from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";
import {
  projectRoot,
  current,
  option,
  playwright,
  json,
  writeJson,
  inside,
  run,
  escapeHtml as esc,
} from "./runtime.mjs";
import { previewServer } from "./serve.mjs";

const root = await fs.realpath(projectRoot());
const { timing, signature } = await current(root);
const stage = option("--stage", "scenes");
if (!["scenes", "export"].includes(stage))
  throw new Error("--stage must be scenes or export");
const { chromium } = await playwright();
const browser = await chromium.launch({ headless: true });
const errors = [],
  results = [];
let local;
try {
  const page = await browser.newPage({
    viewport: { width: timing.video.width, height: timing.video.height },
  });
  page.on("pageerror", (e) => errors.push(e.message));
  if (stage === "scenes") {
    const folder = path.join(root, "work/qa");
    await fs.mkdir(folder, { recursive: true });
    for (const scene of timing.scenes) {
      await page.goto(
        pathToFileURL(path.join(root, "work/scenes", scene.id + ".html")).href,
      );
      await page.evaluate(() => document.fonts.ready);
      await page.waitForFunction(() =>
        [...document.images].every(
          (img) => img.complete && img.naturalWidth > 0,
        ),
      );
      if (await page.locator("video").count())
        await page.waitForFunction(
          () => document.querySelector("video").readyState >= 1,
        );
      const times = [
        ...new Set([
          Math.min(2, scene.duration / 2),
          ...scene.cues.map((c) => (c.start + c.end) / 2),
          Math.max(0, scene.duration - 0.6),
        ]),
      ];
      for (const t of times) {
        await page.evaluate((time) => window.seek(time), t);
        await page.waitForTimeout(100);
        const overflow = await page.evaluate(() =>
          [...document.querySelectorAll(".bounded,.content")]
            .filter((n) => Number(getComputedStyle(n).opacity) > 0.9)
            .filter(
              (n) =>
                n.scrollWidth > n.clientWidth + 6 ||
                n.scrollHeight > n.clientHeight + 6,
            )
            .map((n) => n.textContent.slice(0, 100)),
        );
        errors.push(
          ...overflow.map((text) => `${scene.id}: content overflow: ${text}`),
        );
        const file = `${scene.id}-${t.toFixed(2)}.png`;
        await page.screenshot({ path: path.join(folder, file) });
        results.push({
          scene: scene.id,
          time: t,
          screenshot: `work/qa/${file}`,
        });
      }
      if (scene === timing.scenes[0]) {
        await page.evaluate(() => window.seek(2));
        await page.screenshot({ path: path.join(root, "work/poster.png") });
      }
    }
    await writeJson(path.join(root, "work/scenes-check.json"), {
      source_signature: signature,
      errors,
      frames: results,
    });
  } else {
    const candidate = await json(path.join(root, "work/candidate.json"));
    if (candidate.source_signature !== signature)
      throw new Error("Rendered candidate is stale");
    const qa = await json(path.join(root, "work/scenes-check.json"));
    if (qa.source_signature !== signature || qa.errors.length)
      throw new Error(
        "Run and inspect scene verification before export verification",
      );
    const file = await inside(root, candidate.video);
    const probe = JSON.parse(
      (
        await run("ffprobe", [
          "-v",
          "error",
          "-show_streams",
          "-show_format",
          "-of",
          "json",
          file,
        ])
      ).stdout,
    );
    const video = probe.streams.find((s) => s.codec_type === "video"),
      audio = probe.streams.find((s) => s.codec_type === "audio");
    if (
      !video ||
      !audio ||
      video.width !== timing.video.width ||
      video.height !== timing.video.height
    )
      throw new Error("Missing audio/video or incorrect dimensions");
    if (Math.abs(Number(probe.format.duration) - timing.duration) > 0.2)
      throw new Error("Encoded duration differs from narration timing");
    await run("ffmpeg", [
      "-hide_banner",
      "-v",
      "error",
      "-i",
      file,
      "-f",
      "null",
      "-",
    ]);
    const pcm = (
      await run("ffmpeg", [
        "-hide_banner",
        "-v",
        "error",
        "-i",
        file,
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-f",
        "f32le",
        "pipe:1",
      ])
    ).stdout;
    const cuts = [];
    for (const scene of timing.scenes) {
      const end = scene.start + scene.duration;
      const from = Math.max(
        scene.start + scene.cues.at(-1).end + 0.12,
        end - 0.45,
      );
      const to = end - 0.15;
      if (to - from < 0.05)
        throw new Error(
          `Insufficient end hold to verify ${scene.id}; increase end_hold_seconds`,
        );
      let peak = 0;
      for (
        let i = Math.round(from * 16000);
        i < Math.min(Math.round(to * 16000), pcm.length / 4);
        i++
      )
        peak = Math.max(peak, Math.abs(pcm.readFloatLE(i * 4)));
      if (peak > 0.001)
        throw new Error(
          `Audible signal near ${scene.id} cut; inspect timing and soundtrack`,
        );
      cuts.push({ scene: scene.id, cut: end, peak, end_hold: scene.end_hold });
    }
    const directory = await inside(root, candidate.directory);
    await fs.copyFile(
      path.join(root, "work/poster.png"),
      path.join(directory, "poster.png"),
    );
    const links = timing.scenes
      .map(
        (s) =>
          `<button data-start="${s.start}">${esc(s.title || s.id)}</button>`,
      )
      .join("");
    const review = `<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${esc(timing.title)}</title><style>*{box-sizing:border-box}body{margin:0;background:#f4f8f5;color:#173e31;font:16px/1.6 system-ui,sans-serif}main{max-width:1280px;margin:35px auto;padding:0 22px}video{display:block;width:100%;border-radius:14px;background:#f7faf8}h1{font-size:30px}nav{display:flex;flex-wrap:wrap;gap:10px;margin:20px 0}button{border:1px solid #c6dacd;background:white;border-radius:8px;padding:11px 16px;color:inherit;cursor:pointer}a{color:#087f68;margin-right:20px}p{color:#668472}</style><main><h1>${esc(timing.title)}</h1><p>${esc(timing.voice)} · ${Math.round(timing.duration)} 秒 · ${timing.video.width}×${timing.video.height}</p><video controls preload="metadata" poster="${candidate.directory}/poster.png" src="${candidate.video}"></video><nav>${links}</nav><p><a href="${candidate.video}" download>下载 MP4</a><a href="${candidate.directory}/subtitles.srt" download>下载字幕</a></p></main><script>for(const button of document.querySelectorAll('button'))button.onclick=()=>{const video=document.querySelector('video');video.currentTime=Number(button.dataset.start);video.play().catch(e=>{if(e.name!=='AbortError')throw e;});};</script></html>`;
    // Stage a separate review page until browser playback checks succeed.
    await fs.writeFile(
      path.join(directory, "review.html"),
      review
        .replaceAll('src="exports/', 'src="../../exports/')
        .replaceAll('poster="exports/', 'poster="../../exports/')
        .replaceAll('href="exports/', 'href="../../exports/'),
    );
    local = await previewServer(root);
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto(local.url + candidate.directory + "/review.html");
    await page.waitForFunction(
      () => document.querySelector("video").readyState >= 1,
    );
    await page.evaluate(async () => {
      const v = document.querySelector("video");
      v.muted = true;
      await v.play();
    });
    await page.waitForFunction(
      () => document.querySelector("video").currentTime > 0.3,
    );
    await page.locator("button").last().click();
    await page.waitForFunction(
      (start) => document.querySelector("video").currentTime >= start + 0.3,
      timing.scenes.at(-1).start,
    );
    await page.evaluate(() => document.querySelector("video").pause());
    await page.screenshot({
      path: path.join(directory, "review-desktop.png"),
      fullPage: true,
    });
    await page.setViewportSize({ width: 390, height: 844 });
    if (
      !(await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ))
    )
      throw new Error("Review page overflows on mobile");
    if (errors.length) throw new Error(errors.join("\n"));
    let transcript;
    try {
      transcript = await json(path.join(root, "work/transcript-check.json"));
    } catch {
      /* optional machine evidence */
    }
    const report = {
      source_signature: signature,
      passed: true,
      actual_duration: Number(probe.format.duration),
      dimensions: [video.width, video.height],
      cuts,
      browser_errors: errors,
      transcript_checked: transcript?.source_signature === signature,
      transcript_review_needed: transcript?.review_needed ?? null,
    };
    await writeJson(path.join(directory, "verification.json"), report);
    await fs.writeFile(path.join(root, "review.html"), review);
    await writeJson(path.join(root, "exports/latest.json"), {
      ...candidate,
      verified: true,
    });
    console.log(`Verified and ready for human review: ${candidate.video}`);
  }
  if (errors.length) throw new Error(errors.join("\n"));
  if (stage === "scenes")
    console.log(
      `Inspected ${results.length} scene frames. Review the saved screenshots for visual quality.`,
    );
} finally {
  await browser.close();
  await local?.close();
}
