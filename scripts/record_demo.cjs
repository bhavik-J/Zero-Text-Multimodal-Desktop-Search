#!/usr/bin/env node
/*
 * Records a narrated walkthrough of every PixelIndex feature with Playwright.
 *
 *   node scripts/record_demo.cjs [--url http://127.0.0.1:5173] [--out docs/demo/video]
 *        [--inbox "data/video_inbox/Phone dump"] [--upload path/to/photo.jpg]
 *
 * Needs a running app (./start.sh data/testset) whose library is indexed and
 * whose galaxy is computed. --inbox is a small, not-yet-indexed folder that is
 * added and indexed live on camera. Produces a .webm; convert with ffmpeg.
 */
const path = require('path');
const fs = require('fs');
let playwright;
try { playwright = require('playwright'); } catch { playwright = require('/opt/node22/lib/node_modules/playwright'); }

const ROOT = path.resolve(__dirname, '..');
const arg = (k, d) => { const i = process.argv.indexOf(k); return i > 0 ? process.argv[i + 1] : d; };
const URL = arg('--url', 'http://127.0.0.1:5173');
const OUT = path.resolve(arg('--out', path.join(ROOT, 'docs/demo/video')));
const INBOX = path.resolve(arg('--inbox', path.join(ROOT, 'data/video_inbox/Phone dump')));
const UPLOAD = path.resolve(arg('--upload', path.join(ROOT, 'data/testset/Camera Roll/2024/IMG_4972.jpg')));
const W = 1440, H = 900;

// Visible cursor + caption bar + title cards, injected into every page.
const OVERLAY = () => {
  const install = () => {
    if (document.getElementById('__demo_cursor')) return;
    const css = document.createElement('style');
    css.textContent = `
      #__demo_cursor{position:fixed;z-index:2147483647;width:22px;height:22px;margin:-3px 0 0 -3px;pointer-events:none;
        transition:transform .08s;filter:drop-shadow(0 2px 4px rgba(0,0,0,.6))}
      #__demo_cursor.down{transform:scale(.8)}
      #__demo_ring{position:fixed;z-index:2147483646;width:36px;height:36px;margin:-18px 0 0 -18px;border-radius:50%;
        border:3px solid #a78bfa;opacity:0;pointer-events:none}
      #__demo_ring.go{animation:__ring .5s ease-out}
      @keyframes __ring{from{opacity:.9;transform:scale(.4)}to{opacity:0;transform:scale(1.6)}}
      #__demo_cap{position:fixed;z-index:2147483645;left:50%;bottom:28px;transform:translateX(-50%);max-width:80%;
        background:rgba(15,10,40,.92);border:1px solid rgba(167,139,250,.55);border-radius:16px;padding:12px 22px;
        color:#fff;font:600 21px/1.35 Inter,system-ui,sans-serif;text-align:center;box-shadow:0 10px 40px rgba(0,0,0,.5);
        opacity:0;transition:opacity .35s;pointer-events:none}
      #__demo_cap small{display:block;font-weight:500;font-size:15px;color:#c4b5fd;margin-top:3px}
      #__demo_card{position:fixed;inset:0;z-index:2147483646;display:flex;flex-direction:column;align-items:center;justify-content:center;
        background:radial-gradient(ellipse at center,#1e1b4b 0%,#020617 70%);color:#fff;font-family:Inter,system-ui,sans-serif;
        opacity:0;transition:opacity .6s;pointer-events:none;text-align:center}
      #__demo_card h1{font-size:64px;margin:0 0 12px;background:linear-gradient(90deg,#a78bfa,#60a5fa);-webkit-background-clip:text;color:transparent}
      #__demo_card p{font-size:24px;color:#c7d2fe;margin:6px 0;max-width:1000px}`;
    document.head.appendChild(css);
    const cur = document.createElement('div');
    cur.id = '__demo_cursor';
    cur.innerHTML = '<svg viewBox="0 0 24 24" width="22" height="22"><path d="M3 2l7.5 19 2.6-7.9L21 10.5z" fill="#fff" stroke="#111" stroke-width="1.6" stroke-linejoin="round"/></svg>';
    const ring = document.createElement('div'); ring.id = '__demo_ring';
    const cap = document.createElement('div'); cap.id = '__demo_cap';
    const card = document.createElement('div'); card.id = '__demo_card';
    document.body.append(cur, ring, cap, card);
    document.addEventListener('mousemove', (e) => { cur.style.left = e.clientX + 'px'; cur.style.top = e.clientY + 'px'; }, true);
    document.addEventListener('mousedown', (e) => {
      cur.classList.add('down');
      ring.style.left = e.clientX + 'px'; ring.style.top = e.clientY + 'px';
      ring.classList.remove('go'); void ring.offsetWidth; ring.classList.add('go');
    }, true);
    document.addEventListener('mouseup', () => cur.classList.remove('down'), true);
    window.__caption = (t, sub) => {
      if (!t) { cap.style.opacity = 0; return; }
      cap.innerHTML = t + (sub ? `<small>${sub}</small>` : '');
      cap.style.opacity = 1;
    };
    window.__card = (html) => { if (html) card.innerHTML = html; card.style.opacity = html ? 1 : 0; };
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', install); else install();
};

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await playwright.chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
  const ctx = await browser.newContext({ viewport: { width: W, height: H }, recordVideo: { dir: OUT, size: { width: W, height: H } } });
  await ctx.addInitScript(OVERLAY);
  const page = await ctx.newPage();
  const tVideo = Date.now();
  const cuts = []; // [start, end] seconds of dead time (spinners) to remove in post
  const now = () => (Date.now() - tVideo) / 1000;
  const errors = [];
  page.on('pageerror', (e) => errors.push(e.message));

  const wait = (ms) => page.waitForTimeout(ms);
  let mx = W / 2, my = H / 2;
  const move = async (x, y, steps = 25) => { await page.mouse.move(x, y, { steps }); mx = x; my = y; };
  const center = async (loc) => { const b = await loc.boundingBox(); return [b.x + b.width / 2, b.y + b.height / 2]; };
  const click = async (loc, pause = 250) => {
    await loc.scrollIntoViewIfNeeded();
    const [x, y] = await center(loc);
    await move(x, y); await wait(pause); await page.mouse.down(); await wait(70); await page.mouse.up();
  };
  const type = async (loc, text, delay = 55) => { await click(loc); await page.keyboard.type(text, { delay }); };
  const clearType = async (loc, text) => {
    await click(loc); await page.keyboard.press('Control+A'); await page.keyboard.press('Backspace');
    await page.keyboard.type(text, { delay: 55 });
  };
  const caption = (t, sub) => page.evaluate(([t, s]) => window.__caption && window.__caption(t, s), [t || '', sub || '']);
  const card = (html) => page.evaluate((h) => window.__card && window.__card(h), html || '');
  const tab = (name) => page.locator(`[role="tab"]:has-text("${name}")`).first();
  const scene = (name) => console.log(`[${((Date.now() - t0) / 1000).toFixed(0)}s] ${name}`);
  const t0 = Date.now();

  await page.goto(`${URL}/#library`);
  await wait(1500);
  await move(W / 2, H / 2, 1);

  // ── 0. title ─────────────────────────────────────────────────────────
  scene('title');
  await card(`<h1>PixelIndex</h1><p>Zero-text multimodal desktop search</p>
    <p style="color:#94a3b8;font-size:20px;margin-top:22px">Find any image by vibe, sketch, colour, the text inside it, or similarity —
    100 % local, no cloud</p>`);
  await wait(4200);
  await card('');
  await wait(700);

  // ── 1. library ───────────────────────────────────────────────────────
  scene('library');
  await caption('A messy library: 3,300 photos, screenshots and memes', 'File names like IMG_4972.jpg and download (46).jpg tell you nothing');
  await wait(2500);
  await move(700, 500); await page.mouse.wheel(0, 900); await wait(1300); await page.mouse.wheel(0, 900); await wait(1500);
  await page.mouse.wheel(0, -1800); await wait(800);

  // ── 2. add + index a folder live ─────────────────────────────────────
  scene('indexing');
  await caption('Add a folder and index it', 'Colour palette, OCR text, CLIP embedding and duplicate hashes — all computed locally');
  await click(page.locator('button[title="Add folder"]'));
  await wait(400);
  await page.keyboard.type(INBOX, { delay: 18 });
  await wait(500);
  await click(page.locator('button.btn-primary:has-text("Add")').first());
  await wait(1200);
  await click(page.locator('button[title="Index new & changed files"]'));
  for (let i = 0; i < 40; i++) {
    await wait(1000);
    const n = await page.evaluate(async () => (await (await fetch('/api/v1/folders')).json())
      .reduce((a, f) => a + (f.image_counts.pending || 0), 0));
    if (i > 3 && n === 0) break;
  }
  await caption('Indexed — ready to search', 'Every image is now searchable by meaning, text, colour and look');
  await wait(2500);

  // ── 3. vibe search ───────────────────────────────────────────────────
  scene('vibe search');
  await click(tab('Search'));
  await wait(800);
  const q = page.locator('input[aria-label="Search by description"]');
  await caption('Search by vibe', 'Describe what you remember — CLIP matches meaning, not file names');
  await type(q, 'kids playing in the snow');
  await wait(3200);
  const firstCard = page.locator('main .grid > *').first();
  await move(...(await center(firstCard))); await wait(1800);
  await caption('Each result shows why it matched', 'Score breakdown (semantic · OCR · colour), its colour palette and timing (FAISS < 1 ms)');
  await wait(2600);
  await clearType(q, 'a cozy living room with a fireplace');
  await wait(3500);
  await clearType(q, 'sunset over the ocean');
  await wait(3200);

  // ── 4. colour filter (hybrid) ────────────────────────────────────────
  scene('colour');
  await caption('Mix in a colour palette', 'Hybrid search: meaning + colour, weighted and fused into one ranking');
  const purple = page.locator('button[aria-label^="Add colour"]').nth(9);
  await click(purple); await wait(3200);
  await click(page.locator('button[aria-label^="Remove colour"]').first()); await wait(600);
  await click(page.locator('button[aria-label="Clear text"]')); await wait(800);

  // ── 5. OCR ──────────────────────────────────────────────────────────
  scene('ocr');
  await caption('Find text inside images', 'Lecture slides, memes and code screenshots are OCR-indexed with Tesseract');
  const ocr = page.locator('#ocr-filter');
  await type(ocr, 'gradient descent');
  await wait(3500);
  await clearType(ocr, 'when you');
  await wait(3000);
  await click(ocr); await page.keyboard.press('Control+A'); await page.keyboard.press('Backspace'); await wait(700);

  // ── 6. sketch ───────────────────────────────────────────────────────
  scene('sketch');
  await caption('Sketch what you remember', 'The live sketch-pad searches as you draw');
  const canvas = page.locator('canvas[aria-label^="Sketch canvas"]');
  const cb = await canvas.boundingBox();
  await click(page.locator('button[aria-label="Brush colour #3B82F6"]'));
  await page.keyboard.press(']'); await page.keyboard.press(']');
  for (let r = 0; r < 7; r++) {
    await move(cb.x + 12, cb.y + 130 + r * 16, 6); await page.mouse.down();
    await move(cb.x + cb.width - 12, cb.y + 130 + r * 16, 14); await page.mouse.up();
  }
  await click(page.locator('button[aria-label="Brush colour #FACC15"]'));
  await move(cb.x + cb.width / 2, cb.y + 72, 8); await page.mouse.down();
  for (let a = 0; a <= 48; a++) await move(cb.x + cb.width / 2 + Math.cos(a / 6) * 28, cb.y + 72 + Math.sin(a / 6) * 28, 1);
  await page.mouse.up();
  await wait(3800);
  await caption('Results follow the sketch’s layout and colours', 'Rough strokes are embedded with the same CLIP image encoder + stroke colours');
  await wait(2500);
  await click(page.locator('button:has-text("Reset")').first()); await wait(900);

  // ── 7. image upload ─────────────────────────────────────────────────
  scene('upload');
  await caption('Search with an image', 'Upload, drop or paste any picture to find visually similar ones');
  const [chooser] = await Promise.all([page.waitForEvent('filechooser'), click(page.locator('button[title^="Search by image"]'))]);
  await chooser.setFiles(UPLOAD);
  await wait(3800);

  // ── 8. inspector + find similar ─────────────────────────────────────
  scene('inspector');
  await caption('Inspect any image', 'Metadata, dominant colours, OCR text and embedding info');
  await click(page.locator('main .grid > *').nth(2));
  await wait(2800);
  await caption('Find similar', 'Image-to-image search from the inspector');
  await click(page.locator('button:has-text("Find similar")'));
  await wait(3300);

  // ── 9. galaxy ───────────────────────────────────────────────────────
  scene('galaxy');
  await click(page.locator('main .grid > *').first());
  await wait(1500);
  await caption('Show it in the galaxy', 'Every image placed by meaning — UMAP projection of the CLIP embeddings');
  await click(page.locator('button:has-text("Show in galaxy")'));
  await wait(3500);
  await page.keyboard.press('Escape'); // close the inspector so the galaxy gets the full width
  await wait(800);
  const stale = page.locator('button[title="Recompute projection & clusters"]:has-text("Stale")');
  if (await stale.count()) {
    await caption('New images were indexed — recompute the galaxy', 'UMAP + automatic clustering + zero-shot theme names');
    await click(stale);
    const c0 = now() + 1.5;
    await page.waitForFunction(() => !document.querySelector('button[title="Recompute projection & clusters"]')?.textContent?.includes('Stale'), null, { timeout: 120000 }).catch(() => {});
    cuts.push([c0, now() - 0.3]);
    await wait(2500);
  }
  await click(page.locator('button[title="Fit (0)"]')); await wait(1500);
  await caption('Themes are found and named automatically', 'dogs, food, street, sports, lecture slides, code screenshots… named by CLIP');
  const g = page.locator('canvas[aria-label^="2D galaxy"]');
  const gb = await g.boundingBox();
  await move(gb.x + gb.width * 0.45, gb.y + gb.height * 0.55);
  for (let i = 0; i < 4; i++) { await page.mouse.wheel(0, -240); await wait(250); }
  await wait(1500);
  await caption('Zoom in to see the actual pictures', 'Drag to pan · scroll to zoom · hover for a preview · click to inspect');
  await page.mouse.down(); await move(gb.x + gb.width * 0.6, gb.y + gb.height * 0.45, 30); await page.mouse.up();
  await wait(1200);
  for (let i = 0; i < 3; i++) { await page.mouse.wheel(0, -240); await wait(250); }
  await wait(1800);
  for (let s = 0; s < 14; s++) { await move(gb.x + gb.width * (0.35 + s * 0.02), gb.y + gb.height * (0.45 + (s % 3) * 0.03), 6); await wait(160); }
  await wait(1200);
  await click(page.locator('button[title="Fit (0)"]')); await wait(1500);

  await caption('Click a theme to focus it');
  const legendItems = page.locator('button[aria-pressed]').filter({ has: page.locator('span[title="dog"], span[title="food"]') });
  if (await legendItems.count()) { await click(legendItems.first()); await wait(2800); await click(legendItems.first()); await wait(1000); }

  await caption('Search lights up matches in the galaxy');
  await type(page.locator('input[aria-label="Search and highlight in galaxy"]'), 'beach');
  await wait(3800);
  await click(page.locator('button[aria-label="Clear galaxy search"]')); await wait(800);

  // ── 10. 3D ──────────────────────────────────────────────────────────
  scene('3d');
  await caption('…and in 3D', 'three.js point cloud — orbit, zoom, click any star');
  await click(page.locator('[aria-label="Dimensions"] button:has-text("3D")'));
  await wait(2500);
  const stale3 = page.locator('button[title="Recompute projection & clusters"]:has-text("Stale")');
  if (await stale3.count()) {
    await click(stale3);
    const c1 = now() + 1.5;
    await page.waitForFunction(() => !document.querySelector('button[title="Recompute projection & clusters"]')?.textContent?.includes('Stale'), null, { timeout: 120000 }).catch(() => {});
    cuts.push([c1, now() - 0.3]);
    await wait(1500);
  }
  await click(page.locator('button[title="Auto-rotate"]'));
  await wait(4500);
  const c3 = page.locator('main canvas').first();
  const b3 = await c3.boundingBox();
  await move(b3.x + b3.width * 0.4, b3.y + b3.height * 0.5); await page.mouse.down();
  await move(b3.x + b3.width * 0.6, b3.y + b3.height * 0.4, 40); await page.mouse.up();
  await wait(2500);
  await click(page.locator('button[title="Auto-rotate"]'));
  await click(page.locator('[aria-label="Dimensions"] button:has-text("2D")')); await wait(800);

  // ── 11. duplicates ──────────────────────────────────────────────────
  scene('duplicates');
  await click(tab('Duplicates'));
  await caption('Find duplicates and near-duplicates', 'Exact copies (SHA-256) and edited copies (resized, cropped, re-encoded) — pHash + CLIP + pixel check');
  const c2 = now() + 1.5;
  await page.waitForSelector('text=Reclaimable', { timeout: 60000 }).catch(() => {});
  if (now() - c2 > 1) cuts.push([c2, now() - 0.3]);
  await wait(2500);
  await move(700, 500); await page.mouse.wheel(0, 700); await wait(1800); await page.mouse.wheel(0, -700); await wait(800);
  await click(page.locator('[aria-label="Duplicate kind"] button:has-text("Near")')); await wait(2500);
  await caption('Keeps the largest file, shows how much space you can free');
  await wait(2500);
  await click(page.locator('[aria-label="Duplicate kind"] button:has-text("All")')); await wait(800);

  // ── 12. end ─────────────────────────────────────────────────────────
  scene('end');
  await caption('');
  await card(`<h1>PixelIndex</h1>
    <p>Vibe · Sketch · Colour · Text-in-image · Similar · Galaxy · Duplicates</p>
    <p style="color:#94a3b8;font-size:20px;margin-top:22px">CLIP (ONNX) · FAISS · UMAP · Tesseract · React + three.js — runs entirely on your machine</p>
    <p style="color:#a78bfa;font-size:20px;margin-top:18px">github.com/bhavik-J/Zero-Text-Multimodal-Desktop-Search</p>`);
  await wait(5000);

  const video = page.video();
  await ctx.close();
  await browser.close();
  const src = await video.path();
  const dest = path.join(OUT, 'pixelindex-demo.webm');
  fs.renameSync(src, dest);
  fs.writeFileSync(path.join(OUT, 'cuts.json'), JSON.stringify(cuts.filter(([a, b]) => b > a)));
  console.log('video', dest, 'cuts', JSON.stringify(cuts), 'errors', JSON.stringify(errors));
})();
