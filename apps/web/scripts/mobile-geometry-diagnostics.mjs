import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";

const baseUrl = (process.env.BROWSER_SMOKE_BASE_URL || "http://127.0.0.1:3001").replace(/\/$/, "");
const port = Number(process.env.MOBILE_GEOMETRY_DEBUG_PORT || 9224);
const tokens = JSON.parse(process.env.BROWSER_SMOKE_TOKENS_JSON || "{}");
const browserPath = [
  process.env.BROWSER_BIN,
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  "/usr/bin/google-chrome",
  "/usr/bin/google-chrome-stable",
  "/usr/bin/chromium",
  "/usr/bin/chromium-browser",
].find((candidate) => candidate && existsSync(candidate));

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
    const id = this.nextId++;
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
    try { await this.send("Page.close"); } catch {}
    this.socket.close();
  }
}

async function newPage() {
  const response = await fetch(`http://127.0.0.1:${port}/json/new?${encodeURIComponent("about:blank")}`, { method: "PUT" });
  if (!response.ok) throw new Error(`Could not create Chrome target (${response.status}).`);
  const target = await response.json();
  const session = new CdpSession(target.webSocketDebuggerUrl);
  await session.open();
  await Promise.all([session.send("Page.enable"), session.send("Network.enable"), session.send("Runtime.enable")]);
  return session;
}

async function setCookies(session, role) {
  const token = tokens[role];
  if (!token) throw new Error(`Missing browser smoke token for ${role}`);
  const values = {
    ho_staff_payroll_access_token: token,
    ho_staff_payroll_role: role,
    ho_staff_payroll_name: role === "staff" ? "Staff" : role,
  };
  for (const [name, value] of Object.entries(values)) {
    await session.send("Network.setCookie", { name, value, url: baseUrl, httpOnly: true, sameSite: "Lax" });
  }
}

async function inspect(role, route, selectors) {
  const session = await newPage();
  try {
    await session.send("Emulation.setDeviceMetricsOverride", {
      width: 390,
      height: 844,
      deviceScaleFactor: 2,
      mobile: true,
      scale: 2,
    });
    await setCookies(session, role);
    const loaded = session.waitFor("Page.loadEventFired");
    await session.send("Page.navigate", { url: `${baseUrl}${route}` });
    await loaded;
    await delay(1200);
    const result = await session.send("Runtime.evaluate", {
      returnByValue: true,
      expression: `(() => {
        const snap = (element) => {
          if (!element) return null;
          const rect = element.getBoundingClientRect();
          const style = getComputedStyle(element);
          const parent = element.parentElement;
          const parentRect = parent?.getBoundingClientRect();
          return {
            tag: element.tagName,
            className: String(element.className || ""),
            left: rect.left,
            right: rect.right,
            width: rect.width,
            clientWidth: element.clientWidth,
            scrollWidth: element.scrollWidth,
            computedWidth: style.width,
            minWidth: style.minWidth,
            maxWidth: style.maxWidth,
            marginLeft: style.marginLeft,
            marginRight: style.marginRight,
            paddingLeft: style.paddingLeft,
            paddingRight: style.paddingRight,
            boxSizing: style.boxSizing,
            display: style.display,
            position: style.position,
            parentClassName: String(parent?.className || ""),
            parentLeft: parentRect?.left ?? null,
            parentRight: parentRect?.right ?? null,
            parentWidth: parentRect?.width ?? null,
          };
        };
        const selectors = ${JSON.stringify(selectors)};
        return {
          route: location.pathname,
          windowInnerWidth: window.innerWidth,
          visualViewportWidth: window.visualViewport?.width || null,
          devicePixelRatio: window.devicePixelRatio,
          root: snap(document.documentElement),
          body: snap(document.body),
          main: snap(document.querySelector('main')),
          page: snap(document.querySelector('.page')),
          targets: Object.fromEntries(Object.entries(selectors).map(([name, selector]) => [name, snap(document.querySelector(selector))])),
        };
      })()`,
    });
    console.log(`MOBILE_GEOMETRY ${role} ${route} ${JSON.stringify(result.result?.value || {})}`);
  } finally {
    await session.close();
  }
}

if (!browserPath) {
  console.error("MOBILE_GEOMETRY diagnostic skipped: Chrome or Chromium not found.");
  process.exit(0);
}

const profileDir = await mkdtemp(path.join(os.tmpdir(), "staff-payroll-geometry-chrome-"));
const browser = spawn(browserPath, [
  "--headless=new",
  `--remote-debugging-port=${port}`,
  `--user-data-dir=${profileDir}`,
  "--no-first-run",
  "--disable-background-networking",
  "--disable-component-update",
  "--disable-default-apps",
  "--disable-dev-shm-usage",
  "--no-sandbox",
  "about:blank",
], { stdio: "ignore" });
const browserExit = new Promise((resolve) => browser.once("exit", resolve));

try {
  await waitForChrome();
  await inspect("owner", "/schedule", {
    heading: "header[class*='pageHeading']",
    headingActions: "div[class*='headingActions']",
    kpiGrid: "section[class*='kpiGrid']",
  });
  await inspect("staff", "/me", {
    hero: ".staff-hero",
    actions: ".staff-actions",
    summary: ".staff-summary",
  });
} catch (error) {
  console.error(`MOBILE_GEOMETRY diagnostic failed: ${error instanceof Error ? error.message : String(error)}`);
} finally {
  browser.kill("SIGTERM");
  await Promise.race([browserExit, delay(3000)]);
  if (browser.exitCode === null && browser.signalCode === null) {
    browser.kill("SIGKILL");
    await Promise.race([browserExit, delay(1000)]);
  }
  await rm(profileDir, { recursive: true, force: true, maxRetries: 5, retryDelay: 100 });
}
