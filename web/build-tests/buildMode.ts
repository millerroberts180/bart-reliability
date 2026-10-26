// Builds the site as `vite build` does, for the data mode in VITE_DATA_MODE, into <outDir>,
// and writes the source modules in each output chunk to <report> (JSON, outside the build).
// Run by isolation.test.ts in a fresh process, so the build sees no test-runner settings:
//   node build-tests/buildMode.ts <outDir> <report>

import { writeFile } from 'node:fs/promises';
import path from 'node:path';
import { build } from 'vite';

const [outDir, report] = process.argv.slice(2);
if (!outDir || !report) throw new Error('usage: node build-tests/buildMode.ts <outDir> <report>');

const web = path.resolve(import.meta.dirname, '..');
const result = await build({ root: web, logLevel: 'warn', build: { outDir, emptyOutDir: true } });
const outputs = Array.isArray(result) ? result : [result];

const chunks: { fileName: string; modules: string[] }[] = [];
for (const output of outputs) {
  if (!('output' in output)) throw new Error('Expected a finished build, not a watcher.');
  for (const item of output.output) {
    if (item.type !== 'chunk') continue;
    const modules = item.moduleIds
      .filter((id) => id.startsWith(web) && !id.includes('/node_modules/'))
      .map((id) => path.relative(web, id).split(path.sep).join('/'));
    chunks.push({ fileName: item.fileName, modules });
  }
}
await writeFile(report, JSON.stringify({ chunks }, null, 1));
