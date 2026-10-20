// Small, reproducible deployment changes against the pinned upstream revision.
const fs = require('node:fs');
const path = require('node:path');
const root = process.argv[2];
if (!root) throw new Error('Expected gateway source directory');
function replace(file, before, after) {
  const target = path.join(root, file);
  const source = fs.readFileSync(target, 'utf8');
  if (source.includes(after)) return;
  if (!source.includes(before)) throw new Error(`Upstream changed: ${file}`);
  fs.writeFileSync(target, source.replace(before, after));
}
replace('src/turnstile.js',
  'async function solveTurnstile(page, opts = {}) {',
  'async function solveTurnstile(page, opts = {}) {\n  // Verification is completed by the account owner in /login.\n  if (process.env.HUMAN_VERIFICATION_ONLY === "1") return false;');
replace('src/server.js',
  "const API_KEY = process.env.API_KEY || '';",
  "const API_KEY = process.env.API_KEY || '';\nif (!API_KEY) throw new Error('API_KEY must be configured');");
replace('src/server.js',
  "  app.use('/v1', requireAuth);",
  "  app.use((req, res, next) => req.path === '/health' || req.path === '/health/live' ? next() : requireAuth(req, res, next));");
replace('src/server.js',
  'app.listen(PORT, (err) => {',
  "app.listen(PORT, process.env.BIND_HOST || '127.0.0.1', (err) => {");
console.log('Gateway patched: required auth, protected static files, manual verification, explicit bind host.');
