// 逐頁截圖（puppeteer，借用 mermaid-cli 安裝的瀏覽器）。
// 用法：node tools/shots.js http://127.0.0.1:8150 F:/appdata/ltc_care/shot/prep.json <out_dir>
const path = require("path");
const fs = require("fs");
const puppeteer = require("F:/appdata/ltc_care/mmdc/node_modules/puppeteer");

const [base, prepPath, outDir] = process.argv.slice(2);
const prep = JSON.parse(fs.readFileSync(prepPath, "utf8"));
fs.mkdirSync(outDir, { recursive: true });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function clickText(page, text, tag = "button") {
  return page.evaluate((text, tag) => {
    const el = [...document.querySelectorAll(tag)].find((b) => b.textContent.includes(text));
    if (el) { el.click(); return true; }
    return false;
  }, text, tag);
}

async function shot(page, name, opts = {}) {
  await sleep(opts.wait ?? 900);
  // 整頁截圖時把固定底部導覽列改為靜態，避免蓋在頁中
  await page.addStyleTag({ content: ".mode-banner, .dev-banner, [class*=banner] { display: none !important; }" }).catch(() => {});
  await page.screenshot({ path: path.join(outDir, name + ".png"), fullPage: opts.full === true });
  console.log("shot", name);
}

async function withToken(page, url, token) {
  await page.goto(base + "/liff", { waitUntil: "networkidle0" });
  await page.evaluate((t) => sessionStorage.setItem("ltc_session", t), token);
  await page.goto(url, { waitUntil: "networkidle0" });
}

(async () => {
  const browser = await puppeteer.launch({ headless: true, args: ["--lang=zh-TW", "--use-fake-ui-for-media-stream"] });
  // ── 照服員端（手機尺寸）──
  const m = await browser.newPage();
  await m.setViewport({ width: 390, height: 1000, deviceScaleFactor: 2, isMobile: true, hasTouch: true });
  await m.goto(base + "/liff", { waitUntil: "networkidle0" });
  await shot(m, "liff_00_devlogin");
  await withToken(m, base + "/liff", prep.caregiver_token);
  await shot(m, "liff_01_home");
  await m.goto(base + "/liff/ask", { waitUntil: "networkidle0" });
  await m.type("textarea", "小照你好，302 王先生的家屬要我幫忙代購成藥，機構規定可以嗎？");
  await shot(m, "liff_02_ask");
  await m.goto(base + "/liff/answers/" + prep.qa_answered, { waitUntil: "networkidle0" });
  await shot(m, "liff_03_answer", { wait: 1500 });
  if (await clickText(m, "原文")) await shot(m, "liff_04_answer_source", { wait: 1500 });
  await m.goto(base + "/liff/answers/" + prep.qa_conflict, { waitUntil: "networkidle0" });
  await shot(m, "liff_05_escalated_conflict");
  await m.goto(base + "/liff/answers/" + prep.qa_clinical, { waitUntil: "networkidle0" });
  await shot(m, "liff_06_escalated_clinical");
  await m.goto(base + "/liff/record", { waitUntil: "networkidle0" });
  await shot(m, "liff_07_record");
  await m.goto(base + "/liff/record/" + prep.transcript, { waitUntil: "networkidle0" });
  await shot(m, "liff_08_transcript_draft", { wait: 1500 });
  await m.goto(base + "/liff/report", { waitUntil: "networkidle0" });
  await shot(m, "liff_09_report_step1");
  if (await clickText(m, "家屬額外要求")) { await sleep(600); await shot(m, "liff_10_report_step2"); }
  await m.goto(base + "/liff/cases", { waitUntil: "networkidle0" });
  await shot(m, "liff_11_cases");
  await m.goto(base + "/liff/cases/" + prep.case_conflict, { waitUntil: "networkidle0" });
  await shot(m, "liff_12_case_reply");
  await m.goto(base + "/liff/help", { waitUntil: "networkidle0" });
  await shot(m, "liff_13_help");
  await m.evaluate(() => sessionStorage.clear());
  await m.goto(base + "/liff", { waitUntil: "networkidle0" });
  if (await clickText(m, "stu_cg01")) { await sleep(1500); await shot(m, "liff_14_bind"); }

  // ── 督導後台（桌面尺寸）──
  const d = await browser.newPage();
  await d.setViewport({ width: 1366, height: 900, deviceScaleFactor: 1.5 });
  await d.goto(base + "/admin/login", { waitUntil: "networkidle0" });
  await shot(d, "admin_00_login", { full: false });
  await d.evaluate((t) => sessionStorage.setItem("ltc_session", t), prep.supervisor_token);
  const adminPages = [["cases", "admin_01_cases"], ["cases/" + prep.case_conflict, "admin_02_case_detail"],
    ["documents", "admin_03_documents"], ["categories", "admin_04_categories"], ["metrics", "admin_05_metrics"],
    ["feedback", "admin_06_feedback"], ["users", "admin_07_users"], ["simulator", "admin_08_simulator"]];
  for (const [p, name] of adminPages) {
    await d.goto(base + "/admin/" + p, { waitUntil: "networkidle0" });
    await shot(d, name, { wait: 1200 });
  }
  await browser.close();
})().catch((e) => { console.error(e); process.exit(1); });
