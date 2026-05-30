import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);

const nodeModules = "C:/Users/HONOR/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules";
const pdfjs = await import(pathToFileURL(path.join(nodeModules, "pdfjs-dist/legacy/build/pdf.mjs")).href);
const { createCanvas } = require(path.join(nodeModules, "@napi-rs/canvas"));

const [pdfPath, outDir] = process.argv.slice(2);
if (!pdfPath || !outDir) {
  throw new Error("Usage: node render_pdf_pages.mjs input.pdf output_dir");
}

fs.mkdirSync(outDir, { recursive: true });

const data = new Uint8Array(fs.readFileSync(pdfPath));
const documentTask = pdfjs.getDocument({
  data,
  disableWorker: true,
  useSystemFonts: true,
  cMapUrl: pathToFileURL(path.join(nodeModules, "pdfjs-dist/cmaps/")).href,
  cMapPacked: true,
  standardFontDataUrl: pathToFileURL(path.join(nodeModules, "pdfjs-dist/standard_fonts/")).href,
});

const doc = await documentTask.promise;
console.log(`pages ${doc.numPages}`);

for (let pageNumber = 1; pageNumber <= doc.numPages; pageNumber += 1) {
  const page = await doc.getPage(pageNumber);
  const viewport = page.getViewport({ scale: 2 });
  const canvas = createCanvas(Math.ceil(viewport.width), Math.ceil(viewport.height));
  const context = canvas.getContext("2d");
  await page.render({ canvasContext: context, viewport }).promise;
  const outPath = path.join(outDir, `page-${String(pageNumber).padStart(2, "0")}.png`);
  fs.writeFileSync(outPath, canvas.toBuffer("image/png"));
  console.log(outPath);
}
