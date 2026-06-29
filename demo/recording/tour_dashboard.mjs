#!/usr/bin/env node
/**
 * Timed browser tour for the 2-minute dow chatbot demo.
 *
 * Usage:
 *   node demo/recording/tour_dashboard.mjs http://127.0.0.1:8131/
 *
 * Requires Playwright. Install only if needed:
 *   cd demo/recording
 *   npm install playwright
 */
import { chromium } from 'playwright';

const url = process.argv[2] ?? 'http://127.0.0.1:8131/';
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function moveToLocator(page, locator) {
  await locator.scrollIntoViewIfNeeded().catch(() => {});
  const box = await locator.boundingBox();
  if (!box) return;
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2, { steps: 24 });
  await sleep(350);
}

async function clickIfVisible(page, name, timeout = 2500) {
  const target = page.getByRole('button', { name }).first();
  try {
    await target.waitFor({ state: 'visible', timeout });
    await moveToLocator(page, target);
    await target.click();
    await sleep(400);
    return true;
  } catch {
    return false;
  }
}

async function selectVersion(page, label, value) {
  const select = page.getByLabel(label).first();
  try {
    await moveToLocator(page, select);
    await select.selectOption(value);
    await sleep(400);
    return true;
  } catch {
    return false;
  }
}

async function pointAtText(page, text, timeout = 2500) {
  const target = page.getByText(text).first();
  try {
    await target.waitFor({ state: 'visible', timeout });
    await moveToLocator(page, target);
    return true;
  } catch {
    return false;
  }
}

async function main() {
  const browser = await chromium.launch({ headless: false });
  const page = await browser.newPage({ viewport: { width: 1440, height: 920 } });
  await page.goto(url, { waitUntil: 'networkidle' });

  // 0:30-0:42 Dashboard overview: tree, history, metrics.
  await clickIfVisible(page, /Dashboard/);
  await pointAtText(page, 'Version Tree');
  await sleep(4000);
  await pointAtText(page, 'Version History');
  await sleep(3500);
  await pointAtText(page, /Metrics/);
  await sleep(3500);

  // 0:42-0:54 Version details.
  await clickIfVisible(page, /Version Details/);
  await clickIfVisible(page, /v4|golden|recommend special/i, 2000).catch(() => {});
  await sleep(4500);
  await pointAtText(page, /Sampled outputs|outputs|Config/i).catch(() => {});
  await sleep(5500);

  // 0:54-1:06 Compare.
  await clickIfVisible(page, /Compare/);
  await selectVersion(page, /Baseline|From|A/i, 'v1').catch(() => {});
  await selectVersion(page, /Candidate|To|B/i, 'v4').catch(() => {});
  await pointAtText(page, /Semantic drift|Verdict|Diff/i).catch(() => {});
  await sleep(12000);

  // 1:06-1:14 Dashboard write surface: open editor but do not commit during tour.
  await clickIfVisible(page, /Edit spec/);
  await sleep(3500);
  const note = page.getByLabel(/Change note/i).first();
  await moveToLocator(page, note);
  await note.fill('recording preview').catch(() => {});
  await sleep(2500);
  await clickIfVisible(page, /Close dialog/);
  await sleep(1500);

  await browser.close();
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
