import { chromium } from '@playwright/test';
import { spawn, spawnSync } from 'node:child_process';
import { mkdir } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(__dirname, '..');
const port = Number(process.env.HOME_SCREENSHOT_PORT || 5173);
const baseUrl = `http://127.0.0.1:${port}`;
const outputDir = path.join(root, 'public', 'assets', 'home');

const screens = [
  'my-week',
  'community-clubs',
  'planned-sessions',
  'telegram-chat',
];

async function canReachServer() {
  try {
    const response = await fetch(baseUrl, { method: 'HEAD' });
    return response.ok || response.status < 500;
  } catch {
    return false;
  }
}

async function waitForServer(timeoutMs = 20_000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    if (await canReachServer()) return;
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(`Timed out waiting for Vite at ${baseUrl}`);
}

function startVite() {
  const viteBin = path.join(
    root,
    'node_modules',
    '.bin',
    process.platform === 'win32' ? 'vite.cmd' : 'vite',
  );

  const child = spawn(viteBin, ['--host', '127.0.0.1', '--port', String(port)], {
    cwd: root,
    env: {
      ...process.env,
      BROWSER: 'none',
    },
    stdio: ['pipe', 'pipe', 'pipe'],
    shell: process.platform === 'win32',
  });

  child.stdout.on('data', (chunk) => process.stdout.write(chunk));
  child.stderr.on('data', (chunk) => process.stderr.write(chunk));

  return child;
}

let viteProcess = null;

try {
  if (!(await canReachServer())) {
    viteProcess = startVite();
  }

  await waitForServer();
  await mkdir(outputDir, { recursive: true });

  const browser = await chromium.launch();
  const page = await browser.newPage({
    viewport: { width: 900, height: 1000 },
    deviceScaleFactor: 1,
  });

  for (const screen of screens) {
    await page.goto(`${baseUrl}/__home-screenshots/${screen}`, { waitUntil: 'networkidle' });
    const target = page.locator('.home-shot-capture');
    await target.screenshot({
      path: path.join(outputDir, `${screen}.png`),
    });
    console.log(`Rendered ${screen}.png`);
  }

  await browser.close();
} finally {
  if (viteProcess) {
    if (process.platform === 'win32') {
      spawnSync('taskkill', ['/pid', String(viteProcess.pid), '/T', '/F'], { stdio: 'ignore' });
    } else {
      viteProcess.kill('SIGTERM');
    }
  }
}
