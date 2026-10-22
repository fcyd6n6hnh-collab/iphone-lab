// mobile-mcp smoke test: drive the booted iOS simulator through the MCP server over stdio,
// exactly as an agent would. Checks screenshots work and that a tap really changes the screen.
// usage: node mcp_smoke.mjs <outDir> [--list-only]
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import { writeFileSync, existsSync, statSync, mkdirSync } from "node:fs";
import { createRequire } from "node:module";
import { join, dirname } from "node:path";

const out = process.argv[2] || "results";
const listOnly = process.argv.includes("--list-only");
mkdirSync(out, { recursive: true });
const steps = [];
const step = (name, pass, detail = "") => { steps.push({ name, pass, detail }); console.log(`STEP ${name} => ${pass ? "PASS" : "FAIL"}${detail ? "  " + detail : ""}`); };
const sleep = ms => new Promise(r => setTimeout(r, ms));

const require = createRequire(import.meta.url);
const pkgDir = dirname(require.resolve("@mobilenext/mobile-mcp/package.json"));
const transport = new StdioClientTransport({
  command: process.execPath, args: [join(pkgDir, "lib", "index.js")],
  env: { ...process.env, MOBILEMCP_DISABLE_TELEMETRY: "1" }, stderr: "inherit",
});
const client = new Client({ name: "iphone-lab-smoke", version: "1.0.0" });
const text = r => (r.content || []).filter(c => c.type === "text").map(c => c.text).join("\n");
async function call(name, args = {}) {
  const t0 = Date.now();
  const r = await client.callTool({ name, arguments: args }, undefined, { timeout: 300000 });
  return { r, ms: Date.now() - t0 };
}

let exitCode = 1;
try {
  await client.connect(transport);
  const tools = (await client.listTools()).tools.map(t => t.name);
  writeFileSync(join(out, "tools.txt"), tools.join("\n") + "\n");
  step("server started, tools listed", tools.length > 0, `${tools.length} tools`);
  for (const need of ["mobile_list_available_devices", "mobile_take_screenshot", "mobile_save_screenshot", "mobile_click_on_screen_at_coordinates", "mobile_list_elements_on_screen", "mobile_launch_app"])
    if (!tools.includes(need)) step(`tool ${need} present`, false);
  const dev = await call("mobile_list_available_devices");
  const devText = text(dev.r);
  writeFileSync(join(out, "devices.txt"), devText + "\n");
  if (listOnly) { exitCode = 0; throw "list-only"; }
  const udid = process.env.UDID;
  step("booted simulator listed", !!udid && devText.includes(udid), `${dev.ms} ms`);

  // 1 screenshot as image content (what the model sees)
  const shot = await call("mobile_take_screenshot", { device: udid });
  const img = (shot.r.content || []).find(c => c.type === "image");
  if (img) writeFileSync(join(out, "mcp-01-screenshot.png"), Buffer.from(img.data, "base64"));
  step("mobile_take_screenshot returns an image", !!img && img.data.length > 1000, img ? `${img.mimeType} ${Math.round(img.data.length * 0.75 / 1024)} KB, ${shot.ms} ms` : text(shot.r).slice(0, 300));

  // 2 save screenshot to a file
  const p2 = join(process.cwd(), out, "mcp-02-saved.png");
  const sv = await call("mobile_save_screenshot", { device: udid, saveTo: p2 });
  step("mobile_save_screenshot writes a file", existsSync(p2) && statSync(p2).size > 1000, existsSync(p2) ? `${statSync(p2).size} bytes` : text(sv.r).slice(0, 300));

  // 3 tap test: open Settings, tap "General" by coordinates, expect the General page ("About")
  await call("mobile_launch_app", { device: udid, packageName: "com.apple.Preferences" });
  await sleep(4000);
  const el1 = await call("mobile_list_elements_on_screen", { device: udid, format: "json" });
  const t1 = text(el1.r);
  writeFileSync(join(out, "elements-settings.json"), t1 + "\n");
  let els = [];
  try { els = JSON.parse(t1.slice(t1.indexOf("["), t1.lastIndexOf("]") + 1)); } catch { }
  step("mobile_list_elements_on_screen (Settings)", els.length > 0, `${els.length} elements, ${el1.ms} ms`);
  const label = e => [e.text, e.label, e.name, e.value, e.identifier].filter(Boolean).join(" ");
  const general = els.find(e => /^General$/.test((e.text || e.label || e.name || "").trim())) || els.find(e => /\bGeneral\b/.test(label(e)));
  if (!general) { step("found General row", false, t1.slice(0, 400)); throw "no General"; }
  const r = general.rect || general.coordinates || general;
  const x = Math.round((r.x ?? 0) + (r.width ?? 0) / 2), y = Math.round((r.y ?? 0) + (r.height ?? 0) / 2);
  step("found General row", true, `tap at ${x},${y}`);
  const tap = await call("mobile_click_on_screen_at_coordinates", { device: udid, x, y });
  step("mobile_click_on_screen_at_coordinates", !tap.r.isError, `${text(tap.r).slice(0, 120)} ${tap.ms} ms`);
  await sleep(3000);
  const el2 = await call("mobile_list_elements_on_screen", { device: udid });
  const t2 = text(el2.r);
  writeFileSync(join(out, "elements-after-tap.txt"), t2 + "\n");
  step("tap navigated to General (About visible)", /\bAbout\b/.test(t2) && /Software Update|AirDrop|Date & Time/.test(t2));
  const after = await call("mobile_take_screenshot", { device: udid });
  const img2 = (after.r.content || []).find(c => c.type === "image");
  if (img2) writeFileSync(join(out, "mcp-03-after-tap.png"), Buffer.from(img2.data, "base64"));
  exitCode = steps.every(s => s.pass) ? 0 : 1;
} catch (e) {
  if (e !== "list-only") { console.error("ERROR", e?.stack || e); if (!steps.length || steps.every(s => s.pass)) step("no exception", false, String(e?.message || e).slice(0, 300)); }
} finally {
  writeFileSync(join(out, "mcp-steps.json"), JSON.stringify(steps, null, 1));
  await client.close().catch(() => { });
  console.log(exitCode === 0 ? "MCP SMOKE: PASS" : "MCP SMOKE: FAIL");
  process.exit(exitCode);
}
