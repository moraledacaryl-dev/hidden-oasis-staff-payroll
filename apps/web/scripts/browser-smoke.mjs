import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";

const baseUrl = (process.env.BROWSER_SMOKE_BASE_URL || "http://127.0.0.1:3001").replace(/\/$/, "");
const browserPath = [
  process.env.BROWSER_BIN,
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  "/usr/bin/google-chrome",
  "/usr/bin/google-chrome-stable",
  "/usr/bin/chromium",
  "/usr/bin/chromium-browser",
].find((candidate) => candidate && existsSync(candidate));
const port = Number(process.env.BROWSER_DEBUG_PORT || 9223);
const outputDir = process.env.BROWSER_SMOKE_OUTPUT || path.join(os.tmpdir(), "staff-payroll-browser-smoke");
const tokens = JSON.parse(process.env.BROWSER_SMOKE_TOKENS_JSON || "{}");
const pages = JSON.parse(
  process.env.BROWSER_SMOKE_PAGES_JSON ||
    JSON.stringify({
      owner: ["/", "/cutoff", "/schedule", "/hr", "/backup", "/settings/users"],
      supervisor: ["/", "/attendance", "/schedule/requests", "/cash-advances"],
      staff: ["/me", "/settings/security"],
    }),
);
const viewports = [
  { name: "mobile", width: 390, height: 844, mobile: true, scale: 2 },
  { name: "desktop", width: 1440, height: 900, mobile: false, scale: 1 },
];
const visibleFailurePatterns = [
  /could not be loaded/i,
  /backup failed/i,
  /verification failed/i,
  /not saved/i,
  /application error/i,
  /internal server error/i,
  /failed to fetch/i,
  /something went wrong/i,
];

function delay(ms) { return new Promise((resolve) => setTimeout(resolve, ms)); }

async function waitForChrome() {
  const endpoint = `http://127.0.0.1:${port}/json/version`;
  for (let attempt = 0; attempt < 200; attempt += 1) {
    try {
      const response = await fetch(endpoint);
      if (response.ok) return;
    } catch {
      // Chrome is still starting.
    }
    await delay(150);
  }
  throw new Error(`Chrome DevTools did not start on port ${port}.`);
}

class CdpSession {
  constructor(url) {
    this.socket = new WebSocket(url);
    this.nextId = 1;
    this.pending = new Map();
    this.events = new Map();
  }
  async open() {
    await new Promise((resolve, reject) => {
      this.socket.addEventListener("open", resolve, { once: true });
      this.socket.addEventListener("error", reject, { once: true });
    });
    this.socket.addEventListener("message", (event) => {
      const message = JSON.parse(String(event.data));
      if (message.id) {
        const pending = this.pending.get(message.id);
        if (!pending) return;
        this.pending.delete(message.id);
        if (message.error) pending.reject(new Error(message.error.message));
        else pending.resolve(message.result || {});
        return;
      }
      const waiters = this.events.get(message.method) || [];
      this.events.delete(message.method);
      for (const resolve of waiters) resolve(message.params || {});
    });
  }
  send(method, params = {}) {
    const id = this.nextId;
    this.nextId += 1;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.socket.send(JSON.stringify({ id, method, params }));
    });
  }
  waitFor(method, timeoutMs = 10000) {
    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => reject(new Error(`Timed out waiting for ${method}`)), timeoutMs);
      const wrapped = (value) => { clearTimeout(timeout); resolve(value); };
      this.events.set(method, [...(this.events.get(method) || []), wrapped]);
    });
  }
  async close() {
    try { await this.send("Page.close"); }
    finally { this.socket.close(); }
  }
}

async function newPage() {
  const response = await fetch(`http://127.0.0.1:${port}/json/new?${encodeURIComponent("about:blank")}`, { method: "PUT" });
  if (!response.ok) throw new Error(`Could not create Chrome target (${response.status}).`);
  const target = await response.json();
  const session = new CdpSession(target.webSocketDebuggerUrl);
  await session.open();
  await Promise.all([session.send("Page.enable"), session.send("Network.enable"), session.send("Runtime.enable"), session.send("Log.enable")]);
  return session;
}

async function setSessionCookies(session, role, token) {
  const cookieValues = {
    ho_staff_payroll_access_token: token,
    ho_staff_payroll_role: role,
    ho_staff_payroll_name: role === "supervisor" ? "General Manager" : role,
  };
  for (const [name, value] of Object.entries(cookieValues)) {
    const result = await session.send("Network.setCookie", { name, value, url: baseUrl, httpOnly: true, sameSite: "Lax" });
    if (!result.success) throw new Error(`Could not set ${name}.`);
  }
}

async function inspectPage(session, role, route, viewport) {
  await session.send("Emulation.setDeviceMetricsOverride", { width: viewport.width, height: viewport.height, deviceScaleFactor: viewport.scale, mobile: viewport.mobile, scale: viewport.scale });
  await setSessionCookies(session, role, tokens[role]);
  const loaded = session.waitFor("Page.loadEventFired");
  await session.send("Page.navigate", { url: `${baseUrl}${route}` });
  await loaded;
  await delay(1200);
  const evaluation = await session.send("Runtime.evaluate", {
    returnByValue: true,
    expression: `(() => {
      const root = document.documentElement;
      const text = document.body?.innerText || "";
      const pageOverflow = root.scrollWidth > window.innerWidth + 1;
      const isIntentionalScrollRegion = (element) => {
        for (let node = element; node && node !== document.body; node = node.parentElement) {
          const classes = String(node.className || "");
          if (classes.includes("boardScroll") || classes.includes("matrixGrid") || node.classList?.contains("table-wrap")) return true;
        }
        return false;
      };
      const visibleProblems = [...document.querySelectorAll("body *")].filter((element) => {
        const style = getComputedStyle(element);
        if (style.position === "fixed" || style.position === "absolute") return false;
        if (isIntentionalScrollRegion(element)) return false;
        const rect = element.getBoundingClientRect();
        return rect.width > 0 && (rect.right > window.innerWidth + 2 || rect.left < -2);
      }).slice(0, 10).map((element) => ({ tag: element.tagName, className: String(element.className || "").slice(0, 100), text: String(element.textContent || "").trim().slice(0, 80) }));
      const scheduleClippingProblems = [...document.querySelectorAll("[data-schedule-cell-text]")].filter((element) => (
        element.scrollWidth > element.clientWidth + 1 || element.scrollHeight > element.clientHeight + 1
      )).slice(0, 10).map((element) => ({
        className: String(element.className || "").slice(0, 100),
        text: String(element.textContent || "").trim().slice(0, 80),
        clientWidth: element.clientWidth,
        scrollWidth: element.scrollWidth,
        clientHeight: element.clientHeight,
        scrollHeight: element.scrollHeight,
      }));
      return { href: location.href, title: document.title, text, pageOverflow, scrollWidth: root.scrollWidth, clientWidth: root.clientWidth, visibleProblems, scheduleClippingProblems, hasNextError: Boolean(document.querySelector("nextjs-portal")) };
    })()`,
  });
  const result = evaluation.result?.value || {};
  const matchedFailureText = visibleFailurePatterns.find((pattern) => pattern.test(result.text || ""))?.toString() || null;
  const screenshot = await session.send("Page.captureScreenshot", { format: "png", captureBeyondViewport: false });
  const slug = route === "/" ? "dashboard" : route.replace(/^\/|\/$/g, "").replaceAll("/", "-");
  const file = path.join(outputDir, `${role}-${viewport.name}-${slug}.png`);
  await writeFile(file, Buffer.from(screenshot.data, "base64"));
  let scheduleDropPrompt = null;
  if (role === "owner" && route === "/schedule") {
    const dragStartEvaluation = await session.send("Runtime.evaluate", {
      returnByValue: true,
      expression: `(() => {
        const source = document.querySelector('[data-schedule-shift][draggable="true"]');
        if (!source) return { started: false };
        source.dispatchEvent(new DragEvent("dragstart", { bubbles: true, cancelable: true, dataTransfer: new DataTransfer() }));
        return { started: true };
      })()`,
    });
    await delay(100);
    const dragEvaluation = await session.send("Runtime.evaluate", {
      returnByValue: true,
      expression: `(() => {
        const source = document.querySelector('[data-schedule-shift][draggable="true"]');
        const sourceCell = source?.closest("[data-schedule-cell]");
        const target = [...document.querySelectorAll('[data-schedule-cell][data-drop-enabled="true"]')].find((cell) => (
          cell !== sourceCell &&
          !cell.querySelector("[data-schedule-shift]")
        ));
        if (!${Boolean(dragStartEvaluation.result?.value?.started)} || !source || !target) return { dispatched: false };
        const transfer = new DataTransfer();
        target.dispatchEvent(new DragEvent("dragover", { bubbles: true, cancelable: true, dataTransfer: transfer }));
        target.dispatchEvent(new DragEvent("drop", { bubbles: true, cancelable: true, dataTransfer: transfer }));
        source.dispatchEvent(new DragEvent("dragend", { bubbles: true, cancelable: true, dataTransfer: transfer }));
        return { dispatched: true };
      })()`,
    });
    await delay(200);
    const promptEvaluation = await session.send("Runtime.evaluate", {
      returnByValue: true,
      expression: `(() => {
        const dialog = document.querySelector('[role="dialog"][aria-labelledby="schedule-drop-title"]');
        const buttons = dialog ? [...dialog.querySelectorAll("button")].map((button) => button.textContent?.trim() || button.getAttribute("aria-label")) : [];
        const rect = dialog?.getBoundingClientRect();
        return {
          dispatched: ${Boolean(dragEvaluation.result?.value?.dispatched)},
          visible: Boolean(dialog && rect && rect.width > 0 && rect.height > 0),
          buttons,
          fitsViewport: Boolean(rect && rect.left >= 0 && rect.top >= 0 && rect.right <= window.innerWidth && rect.bottom <= window.innerHeight),
        };
      })()`,
    });
    scheduleDropPrompt = promptEvaluation.result?.value || {};
    const promptScreenshot = await session.send("Page.captureScreenshot", { format: "png", captureBeyondViewport: false });
    await writeFile(
      path.join(outputDir, `${role}-${viewport.name}-${slug}-move-copy.png`),
      Buffer.from(promptScreenshot.data, "base64"),
    );
    await session.send("Runtime.evaluate", {
      expression: `document.querySelector('[role="dialog"] button:last-of-type')?.click()`,
    });
  }
  let cutoffWorkflow = null;
  if (role === "owner" && route === "/cutoff") {
    const cutoffEvaluation = await session.send("Runtime.evaluate", {
      returnByValue: true,
      expression: `(() => {
        const selector = document.querySelector("[data-cutoff-selector]");
        const month = document.querySelector('input[name="month"]');
        const half = document.querySelector('select[name="half"]');
        return {
          selector: Boolean(selector),
          month: Boolean(month?.value),
          half: half?.value === "first" || half?.value === "second",
          completedDefault: selector?.getAttribute("data-period-complete") === "true",
          createDraft: [...document.querySelectorAll("button")].some((button) => button.textContent?.includes("Create payroll draft") && !button.disabled),
        };
      })()`,
    });
    cutoffWorkflow = cutoffEvaluation.result?.value || {};
  }
  return {
    role,
    route,
    viewport: viewport.name,
    screenshot: file,
    ...result,
    matchedFailureText,
    scheduleDropPrompt,
    cutoffWorkflow,
    ok: result.href?.startsWith(`${baseUrl}${route}`) &&
      !result.pageOverflow &&
      !result.hasNextError &&
      (result.visibleProblems || []).length === 0 &&
      (result.scheduleClippingProblems || []).length === 0 &&
      !matchedFailureText &&
      (!scheduleDropPrompt || (
        scheduleDropPrompt.dispatched &&
        scheduleDropPrompt.visible &&
        scheduleDropPrompt.fitsViewport &&
        ["Move", "Copy", "Cancel"].every((label) => scheduleDropPrompt.buttons.includes(label))
      )) &&
      (!cutoffWorkflow || Object.values(cutoffWorkflow).every(Boolean)),
  };
}

if (!tokens.owner || !tokens.supervisor || !tokens.staff) throw new Error("BROWSER_SMOKE_TOKENS_JSON must include owner, supervisor, and staff tokens.");
if (!browserPath) throw new Error("Chrome or Chromium was not found. Set BROWSER_BIN to the browser executable.");

await mkdir(outputDir, { recursive: true });
const profileDir = await mkdtemp(path.join(os.tmpdir(), "staff-payroll-chrome-"));
const browser = spawn(browserPath, ["--headless=new", `--remote-debugging-port=${port}`, `--user-data-dir=${profileDir}`, "--no-first-run", "--disable-background-networking", "--disable-component-update", "--disable-default-apps", "--disable-dev-shm-usage", "--no-sandbox", "about:blank"], { stdio: "ignore" });
const browserExit = new Promise((resolve) => browser.once("exit", resolve));
const results = [];
try {
  await waitForChrome();
  for (const viewport of viewports) {
    for (const [role, routes] of Object.entries(pages)) {
      for (const route of routes) {
        const session = await newPage();
        try { results.push(await inspectPage(session, role, route, viewport)); }
        finally { await session.close(); }
      }
    }
  }
} finally {
  browser.kill("SIGTERM");
  await Promise.race([browserExit, delay(5000)]);
  if (browser.exitCode === null && browser.signalCode === null) {
    browser.kill("SIGKILL");
    await Promise.race([browserExit, delay(2000)]);
  }
  await rm(profileDir, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
}

console.log(JSON.stringify(results, null, 2));
const failures = results.filter((result) => !result.ok);
if (failures.length) {
  for (const failure of failures) {
    if ((failure.visibleProblems || []).length) console.error(`Visible layout problems on ${failure.role} ${failure.viewport} ${failure.route}: ${JSON.stringify(failure.visibleProblems)}`);
    if ((failure.scheduleClippingProblems || []).length) console.error(`Clipped schedule text on ${failure.role} ${failure.viewport} ${failure.route}: ${JSON.stringify(failure.scheduleClippingProblems)}`);
    if (failure.matchedFailureText) console.error(`Visible failure text on ${failure.role} ${failure.viewport} ${failure.route}: ${failure.matchedFailureText}`);
    if (failure.scheduleDropPrompt) console.error(`Move/copy prompt problem on ${failure.role} ${failure.viewport} ${failure.route}: ${JSON.stringify(failure.scheduleDropPrompt)}`);
    if (failure.cutoffWorkflow) console.error(`Payroll cutoff problem on ${failure.role} ${failure.viewport} ${failure.route}: ${JSON.stringify(failure.cutoffWorkflow)}`);
  }
  console.error(`Browser smoke failed on ${failures.length} page(s).`);
  process.exitCode = 1;
}
