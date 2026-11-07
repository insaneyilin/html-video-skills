import fs from "node:fs/promises";
import path from "node:path";
import { projectRoot, option, playwright, inside } from "./runtime.mjs";

const root = await fs.realpath(projectRoot());
const url = option("--url"),
  output = option("--output", "assets/capture.png");
if (!url) throw new Error("--url is required");
const destination = await inside(root, output, false);
await fs.mkdir(path.dirname(destination), { recursive: true });
// Re-resolve after creation to catch a symlink in the destination parent.
const parent = await fs.realpath(path.dirname(destination));
if (parent !== root && !parent.startsWith(root + path.sep))
  throw new Error("Capture output leaves the project");
const { chromium } = await playwright();
const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage({
    viewport: {
      width: Number(option("--width", 1440)),
      height: Number(option("--height", 900)),
    },
  });
  await page.goto(url, { waitUntil: "domcontentloaded" });
  await page.evaluate(() => document.fonts.ready);
  const selector = option("--selector");
  if (selector) await page.locator(selector).screenshot({ path: destination });
  else
    await page.screenshot({
      path: destination,
      fullPage: process.argv.includes("--full-page"),
    });
  console.log(`Captured ${output}`);
} finally {
  await browser.close();
}
