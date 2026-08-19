/*
  Copies pinned official browser bundles into GitDesk's packaged UI directory.
*/

import { copyFile, mkdir } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";


const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const projectRoot = resolve(scriptDirectory, "..");
const uiDirectory = resolve(projectRoot, "src", "gitdesk", "ui");
const noticesDirectory = resolve(projectRoot, "third_party_licenses");

const assets = [
  {
    source: resolve(projectRoot, "node_modules", "dompurify", "dist", "purify.min.js"),
    destination: resolve(uiDirectory, "vendor-dompurify.js"),
  },
  {
    source: resolve(projectRoot, "node_modules", "marked", "lib", "marked.umd.js"),
    destination: resolve(uiDirectory, "vendor-marked.js"),
  },
  {
    source: resolve(projectRoot, "node_modules", "dompurify", "LICENSE"),
    destination: resolve(noticesDirectory, "DOMPurify.txt"),
  },
  {
    source: resolve(projectRoot, "node_modules", "dompurify", "LICENSE-MPL"),
    destination: resolve(noticesDirectory, "DOMPurify-MPL.txt"),
  },
  {
    source: resolve(projectRoot, "node_modules", "marked", "LICENSE"),
    destination: resolve(noticesDirectory, "Marked.txt"),
  },
];

await mkdir(uiDirectory, { recursive: true });
await mkdir(noticesDirectory, { recursive: true });
await Promise.all(assets.map((asset) => copyFile(asset.source, asset.destination)));
