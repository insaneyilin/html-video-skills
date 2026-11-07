import fs from "node:fs/promises";
import path from "node:path";
import {
  projectRoot,
  current,
  inside,
  writeJson,
  escapeHtml as esc,
  scriptJson,
} from "./runtime.mjs";

const root = await fs.realpath(projectRoot());
const { project, timing, signature } = await current(root);
const directory = path.join(root, "work/scenes");
await fs.mkdir(directory, { recursive: true });
async function media(relative) {
  const file = await inside(root, relative),
    extension = path.extname(file).toLowerCase();
  const types = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
  };
  if (!types[extension])
    throw new Error(`Unsupported media extension ${extension}`);
  return (
    `data:${types[extension]};base64,` +
    (await fs.readFile(file)).toString("base64")
  );
}
const graph = {
  schemaVersion: 1,
  intent: "explainer",
  synopsis: project.title,
  nodes: [],
  edges: [],
};
for (const [index, scene] of timing.scenes.entries()) {
  let body;
  const kind = scene.kind || "steps";
  if (kind === "image")
    body = `<img class="media" src="${await media(scene.media)}" alt="${esc(scene.title)}">`;
  else if (kind === "video")
    body = `<video class="media" muted playsinline preload="auto" data-start="${scene.marks.video}" ${scene.poster ? `poster="${await media(scene.poster)}"` : ""} src="${await media(scene.media)}"></video>`;
  else if (kind === "code")
    body = `<pre class="bounded code reveal" data-at="0.5">${esc(scene.code)}</pre>`;
  else if (kind === "title")
    body = `<div class="hero bounded reveal" data-at="0.6">${esc(scene.headline || scene.title)}<p>${esc(scene.subtitle || "")}</p></div>`;
  else
    body = `<div class="cards">${(scene.items || scene.narration)
      .map((item, i) => {
        const text = typeof item === "string" ? item : item.text;
        const at =
          typeof item === "object" && Number.isInteger(item.cue)
            ? (scene.cues[item.cue]?.start ?? 0.5)
            : 0.5 + i * 0.45;
        return `<article class="bounded reveal" data-at="${at}"><span>${String(i + 1).padStart(2, "0")}</span><h2>${esc(text)}</h2></article>`;
      })
      .join("")}</div>`;
  const scale = Math.min(timing.video.width, timing.video.height) / 1080;
  const data = {
    cues: scene.cues,
    duration: scene.duration,
    start: scene.start,
    total: timing.duration,
  };
  const html = `<!doctype html><html lang="${project.language === "Chinese" ? "zh-CN" : "en"}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${esc(scene.title || scene.id)}</title><style>
*{box-sizing:border-box}html,body{margin:0;width:100%;height:100%;overflow:hidden;background:#f5f8f6;color:#193b31;font-family:system-ui,"PingFang SC","Noto Sans CJK SC",sans-serif}#stage{position:absolute;left:0;top:0;width:${timing.video.width}px;height:${timing.video.height}px;transform-origin:0 0;padding:4%;display:flex;flex-direction:column;gap:${26 * scale}px;background:#f7faf8}header{display:flex;justify-content:space-between;gap:20px;padding-bottom:${24 * scale}px;border-bottom:1px solid #cddfd3;font-size:${24 * scale}px;color:#557665}.brand{color:${timing.video.accent || "#087f68"};font-weight:650}h1{margin:0;font-size:${58 * scale}px;font-weight:650;line-height:1.25}.content{flex:1;min-height:0;display:flex;align-items:center;justify-content:center;overflow:hidden}.cards{display:grid;grid-auto-columns:minmax(0,1fr);grid-auto-flow:column;gap:${28 * scale}px;width:100%}article{padding:${42 * scale}px;border:1px solid #cadfd1;background:white;border-radius:${18 * scale}px;min-height:${300 * scale}px}article span{font-size:${26 * scale}px;color:${timing.video.accent || "#087f68"}}article h2{font-size:${43 * scale}px;line-height:1.45;margin:${35 * scale}px 0 0;overflow-wrap:anywhere}.media{max-width:100%;max-height:100%;object-fit:contain;border:1px solid #c9ddd0;border-radius:${15 * scale}px;background:white}.code{width:100%;max-height:100%;padding:${40 * scale}px;background:#183c31;color:#edf6f0;border-radius:15px;font:${28 * scale}px/1.65 monospace;white-space:pre-wrap;overflow-wrap:anywhere}.hero{font-size:${88 * scale}px;line-height:1.2;width:100%;color:${timing.video.accent || "#087f68"}}.hero p{font-size:${35 * scale}px;color:#62816e}.caption{min-height:${85 * scale}px;font-size:${30 * scale}px;line-height:1.4;padding:${16 * scale}px ${25 * scale}px;border-radius:10px;background:#173e31;color:white;text-align:center;opacity:0}.footer{display:flex;justify-content:space-between;font-size:${18 * scale}px;color:#789083}.reveal{opacity:0}.progress{position:absolute;left:0;bottom:0;height:5px;background:${timing.video.accent || "#087f68"};width:0}.veil{position:absolute;inset:0;background:#f7faf8;pointer-events:none}@media(max-aspect-ratio:1/1){.cards{grid-auto-flow:row;grid-auto-columns:unset;grid-template-columns:1fr}article{min-height:0}.hero{font-size:${72 * scale}px}}
</style></head><body><main id="stage"><header><span class="brand">${esc(project.title)}</span><span>${String(index + 1).padStart(2, "0")} / ${timing.scenes.length}</span></header><h1 class="bounded reveal" data-at="0.15">${esc(scene.title || scene.id)}</h1><section class="content">${body}</section><div class="caption bounded" id="caption"></div><footer class="footer"><span>${esc(scene.footer || "DEMO / EXPLAINER")}</span><span>${esc(project.title)}</span></footer><div class="progress" id="progress"></div><div class="veil" id="veil"></div></main><script>
const scene=${scriptJson(data)},nodes=[...document.querySelectorAll('[data-at]')];let playing=false,raf=0,videoStarted=false;
const clamp=x=>Math.max(0,Math.min(1,x));
function paint(t,manual=false){for(const node of nodes){const p=1-Math.pow(1-clamp((t-Number(node.dataset.at))/.65),3);node.style.opacity=p;node.style.transform='translateY('+((1-p)*18)+'px)';}const cue=scene.cues.find(c=>t>=c.start&&t<c.end),caption=document.getElementById('caption');caption.textContent=cue?.text||'';caption.style.opacity=cue?1:0;document.getElementById('progress').style.width=(100*(scene.start+t)/scene.total)+'%';document.getElementById('veil').style.opacity=t<.15?1-t/.15:clamp((t-scene.duration+.22)/.22);const video=document.querySelector('video');if(video){const start=Number(video.dataset.start);if(manual){video.pause();if(Number.isFinite(video.duration))video.currentTime=Math.min(Math.max(0,t-start),Math.max(0,video.duration-.04));}else if(t>=start&&!videoStarted){videoStarted=true;video.currentTime=0;video.play().catch(()=>{});}}}
window.seek=t=>{playing=false;cancelAnimationFrame(raf);paint(t,true);};window.__hvPlayAll=()=>{if(playing)return;playing=true;videoStarted=false;const start=performance.now();const tick=now=>{if(!playing)return;const t=Math.min((now-start)/1000,scene.duration);paint(t);if(t<scene.duration)raf=requestAnimationFrame(tick);};raf=requestAnimationFrame(tick);};function fit(){document.getElementById('stage').style.transform='scale('+Math.min(innerWidth/${timing.video.width},innerHeight/${timing.video.height})+')';}addEventListener('resize',fit);fit();paint(0);if(new URLSearchParams(location.search).get('play')==='1')document.fonts.ready.then(()=>window.__hvPlayAll());
</script></body></html>`;
  await fs.writeFile(path.join(directory, scene.id + ".html"), html);
  graph.nodes.push({
    id: scene.id,
    kind: "text",
    label: scene.title || scene.id,
    text: scene.narration.join("\n"),
    durationSec: scene.duration,
  });
  if (index)
    graph.edges.push({
      from: timing.scenes[index - 1].id,
      to: scene.id,
      kind: "sequence",
    });
}
await writeJson(path.join(root, "work/content-graph.json"), graph);
await writeJson(path.join(root, "work/composed.json"), {
  source_signature: signature,
  scenes: timing.scenes.map((s) => s.id),
});
console.log(
  `Composed ${timing.scenes.length} scenes (${timing.duration.toFixed(2)}s).`,
);
