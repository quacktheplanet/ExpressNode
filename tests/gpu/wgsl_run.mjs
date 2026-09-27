// Run WGSL kernels on the GPU through WebGPU in headless Edge/Chrome.
//
//   node tests/gpu/wgsl_run.mjs job.json out.json [puppeteer_dir]
//
// job.json: {"cases": [{"name", "source", "points": [f32...],
//            "uniforms": [{"type": "f32"|"i32", "value"}...]}]}
// out.json: {"adapter": "...", "results": {name: {"out": [...], "ms",
//            "error"}}}
//
// puppeteer-core is loaded from puppeteer_dir (a folder with
// node_modules/puppeteer-core), or $PUPPETEER_CORE_DIR, or normal
// resolution. The browser is found at $BROWSER or the usual Edge path.

import { createRequire } from "node:module";
import { readFileSync, writeFileSync } from "node:fs";
import http from "node:http";
import path from "node:path";

const [jobPath, outPath, pupDir] = process.argv.slice(2);
const base = pupDir || process.env.PUPPETEER_CORE_DIR || process.cwd();
const require = createRequire(path.join(base, "package.json"));
const puppeteer = require("puppeteer-core");

const job = JSON.parse(readFileSync(jobPath, "utf8"));
const browserPath = process.env.BROWSER ||
  "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";

// WebGPU needs a secure context: serve a blank page from localhost.
const server = http.createServer((req, res) => {
  res.writeHead(200, { "content-type": "text/html" });
  res.end("<!doctype html><title>wgsl</title>");
});
await new Promise((r) => server.listen(0, "127.0.0.1", r));
const port = server.address().port;

const browser = await puppeteer.launch({
  executablePath: browserPath,
  headless: "new",
  args: ["--enable-unsafe-webgpu", "--use-angle=d3d11",
         "--ignore-gpu-blocklist"],
});
try {
  const page = await browser.newPage();
  await page.goto(`http://127.0.0.1:${port}/`);
  const out = await page.evaluate(async (job) => {
    if (!navigator.gpu) return { error: "navigator.gpu missing" };
    const adapter = await navigator.gpu.requestAdapter({ powerPreference: "high-performance" });
    if (!adapter) return { error: "no WebGPU adapter" };
    const device = await adapter.requestDevice({
      requiredLimits: {
        maxStorageBufferBindingSize: adapter.limits.maxStorageBufferBindingSize,
        maxBufferSize: adapter.limits.maxBufferSize,
      },
    });
    const info = adapter.info || {};
    const results = {};
    for (const c of job.cases) {
      try {
        const module = device.createShaderModule({ code: c.source });
        const ci = await module.getCompilationInfo();
        const errs = ci.messages.filter((m) => m.type === "error");
        if (errs.length) {
          results[c.name] = { error: errs.map((m) => `${m.lineNum}:${m.linePos} ${m.message}`).join("; ") };
          continue;
        }
        const pts = new Float32Array(c.points);
        const n = pts.length / 3;
        const inBuf = device.createBuffer({ size: pts.byteLength, usage: GPUBufferUsage.STORAGE | GPUBufferUsage.COPY_DST });
        device.queue.writeBuffer(inBuf, 0, pts);
        const outBuf = device.createBuffer({ size: pts.byteLength, usage: GPUBufferUsage.STORAGE | GPUBufferUsage.COPY_SRC });
        const uSize = Math.max(16, Math.ceil(c.uniforms.length * 4 / 16) * 16);
        const uData = new ArrayBuffer(uSize);
        const f = new Float32Array(uData), i32 = new Int32Array(uData);
        c.uniforms.forEach((u, k) => { if (u.type === "i32") i32[k] = u.value; else f[k] = u.value; });
        const uBuf = device.createBuffer({ size: uSize, usage: GPUBufferUsage.UNIFORM | GPUBufferUsage.COPY_DST });
        device.queue.writeBuffer(uBuf, 0, uData);
        device.pushErrorScope("validation");
        const pipeline = device.createComputePipeline({ layout: "auto", compute: { module, entryPoint: "main" } });
        const bind = device.createBindGroup({
          layout: pipeline.getBindGroupLayout(0),
          entries: [
            { binding: 0, resource: { buffer: inBuf } },
            { binding: 1, resource: { buffer: outBuf } },
            { binding: 2, resource: { buffer: uBuf } },
          ],
        });
        const read = device.createBuffer({ size: pts.byteLength, usage: GPUBufferUsage.MAP_READ | GPUBufferUsage.COPY_DST });
        const groups = Math.ceil(n / 64);
        const gx = Math.min(groups, 65535), gy = Math.ceil(groups / 65535);
        if (gy > 1) throw new Error("too many points for a 1D dispatch");
        const t0 = performance.now();
        const enc = device.createCommandEncoder();
        const pass = enc.beginComputePass();
        pass.setPipeline(pipeline);
        pass.setBindGroup(0, bind);
        pass.dispatchWorkgroups(gx);
        pass.end();
        enc.copyBufferToBuffer(outBuf, 0, read, 0, pts.byteLength);
        device.queue.submit([enc.finish()]);
        await device.queue.onSubmittedWorkDone();
        const ms = performance.now() - t0;
        const verr = await device.popErrorScope();
        if (verr) { results[c.name] = { error: verr.message }; continue; }
        await read.mapAsync(GPUMapMode.READ);
        const arr = new Float32Array(read.getMappedRange().slice(0));
        read.unmap();
        const keep = c.return_count ? arr.slice(0, c.return_count * 3) : arr;
        results[c.name] = { out: Array.from(keep), ms, n };
      } catch (e) {
        results[c.name] = { error: String(e && e.message || e) };
      }
    }
    return { adapter: `${info.vendor || ""} ${info.architecture || ""} ${info.description || ""}`.trim(), results };
  }, job);
  writeFileSync(outPath, JSON.stringify(out));
} finally {
  await browser.close();
  server.close();
}
