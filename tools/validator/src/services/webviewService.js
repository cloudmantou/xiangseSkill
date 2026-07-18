import { JSDOM } from "jsdom";
import { config as appConfig } from "../config.js";
import { performHttpRequest } from "./httpService.js";

function toLowerText(v) {
  return String(v || "").toLowerCase();
}

function toSeconds(v, fallback) {
  const n = Number(v);
  if (!Number.isFinite(n) || n < 0) return fallback;
  return n;
}

function toStringArray(v) {
  if (Array.isArray(v)) return v.map((x) => String(x || "").trim()).filter(Boolean);
  if (typeof v === "string") {
    return v
      .split(/\r?\n|,/g)
      .map((x) => x.trim())
      .filter(Boolean);
  }
  return [];
}

function normalizeDelaySeconds(request) {
  return toSeconds(request?.webViewJsDelay, 0);
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function detectBlocked(status, body, headers) {
  const bodyText = toLowerText(body);
  const cfMitigated = toLowerText(headers?.["cf-mitigated"]);

  if (status === 429) {
    return "HTTP 429 rate limited";
  }
  if (status === 403) {
    if (cfMitigated.includes("challenge")) {
      return "HTTP 403 blocked by Cloudflare challenge";
    }
    if (
      bodyText.includes("cloudflare") ||
      bodyText.includes("just a moment") ||
      bodyText.includes("attention required") ||
      bodyText.includes("challenge")
    ) {
      return "HTTP 403 blocked by anti-bot challenge";
    }
    return "HTTP 403 forbidden";
  }
  if (cfMitigated.includes("challenge")) {
    return "Blocked by challenge middleware (cf-mitigated)";
  }
  return "";
}

async function executeWebviewJsFallback(body, request, trace) {
  const jsCode = String(request?.webViewJs || "").trim();
  if (!jsCode) {
    return { body, jsResult: null };
  }
  const dom = new JSDOM(String(body || ""), {
    url: request.url || "https://example.com/",
    runScripts: "outside-only"
  });
  let jsResult = null;
  try {
    jsResult = dom.window.eval(jsCode);
    trace.push({
      type: "webview_js_eval_fallback",
      ok: true
    });
  } catch (error) {
    trace.push({
      type: "webview_js_eval_fallback",
      ok: false,
      message: error?.message || String(error)
    });
    throw error;
  }
  return {
    body: dom.serialize(),
    jsResult
  };
}

async function performFallbackWebView(request, timeoutMs) {
  const trace = [
    {
      type: "webview_engine_fallback",
      message: "Playwright runtime unavailable; fallback to HTTP + JSDOM"
    }
  ];

  const httpResult = await performHttpRequest(request);
  trace.push({
    type: "http_fetch",
    url: request.url,
    status: httpResult.status
  });

  const delaySeconds = normalizeDelaySeconds(request);
  if (delaySeconds > 0) {
    await delay(delaySeconds * 1000);
    trace.push({ type: "webview_js_delay", seconds: delaySeconds });
  }

  const jsApplied = await executeWebviewJsFallback(httpResult.body, request, trace);
  const blockedReason = detectBlocked(
    httpResult.status,
    jsApplied.body,
    httpResult.headers || {}
  );

  return {
    body: jsApplied.body,
    responseUrl: httpResult.responseUrl || request.url,
    status: httpResult.status,
    headers: httpResult.headers || {},
    blockedReason,
    trace,
    runtimeEngine: "webview:fallback",
    timeoutMs
  };
}

function shouldSkipUrl(url, request) {
  const skip = toStringArray(request?.webViewSkipUrls);
  const unless = toStringArray(request?.webViewSkipUrlsUnless);
  const text = String(url || "");
  if (unless.some((x) => text.includes(x))) return false;
  if (skip.some((x) => text.includes(x))) return true;
  return false;
}

async function performPlaywrightWebView(request, timeoutMs) {
  const trace = [];
  const { chromium } = await import("playwright");
  const browser = await chromium.launch({
    headless: appConfig.webViewHeadless
  });

  try {
    const context = await browser.newContext({
      extraHTTPHeaders: request?.httpHeaders || {}
    });
    const page = await context.newPage();

    page.on("request", (req) => {
      trace.push({
        type: "request",
        method: req.method(),
        url: req.url()
      });
    });
    page.on("response", (res) => {
      trace.push({
        type: "response",
        status: res.status(),
        url: res.url()
      });
    });
    page.on("framenavigated", (frame) => {
      if (frame === page.mainFrame()) {
        trace.push({
          type: "navigated",
          url: frame.url()
        });
      }
    });

    if (request?.webViewSkipUrls || request?.webViewSkipUrlsUnless) {
      await page.route("**/*", async (route) => {
        const url = route.request().url();
        if (shouldSkipUrl(url, request)) {
          trace.push({
            type: "skip_url",
            url
          });
          await route.abort();
          return;
        }
        await route.continue();
      });
    }

    let mainResponse = null;
    if (String(request?.method || "GET").toUpperCase() === "POST") {
      await page.goto("about:blank", { waitUntil: "domcontentloaded", timeout: timeoutMs });
      [mainResponse] = await Promise.all([
        page.waitForNavigation({ waitUntil: "domcontentloaded", timeout: timeoutMs }),
        page.evaluate(
          ({ url, params }) => {
            const form = document.createElement("form");
            form.setAttribute("method", "POST");
            form.setAttribute("action", url);
            for (const [key, value] of Object.entries(params || {})) {
              const input = document.createElement("input");
              input.type = "hidden";
              input.name = key;
              input.value = String(value ?? "");
              form.appendChild(input);
            }
            document.body.appendChild(form);
            form.submit();
          },
          { url: request.url, params: request.httpParams || {} }
        )
      ]);
    } else {
      mainResponse = await page.goto(request.url, {
        waitUntil: "domcontentloaded",
        timeout: timeoutMs
      });
    }

    const delaySeconds = normalizeDelaySeconds(request);
    if (delaySeconds > 0) {
      await delay(delaySeconds * 1000);
      trace.push({
        type: "webview_js_delay",
        seconds: delaySeconds
      });
    }

    const jsCode = String(request?.webViewJs || "").trim();
    if (jsCode) {
      try {
        await page.evaluate(jsCode);
        trace.push({
          type: "webview_js_eval",
          ok: true
        });
      } catch (error) {
        trace.push({
          type: "webview_js_eval",
          ok: false,
          message: error?.message || String(error)
        });
        throw error;
      }
    }

    const body = await page.content();
    const responseUrl = page.url();
    const status = mainResponse ? mainResponse.status() : 200;
    const headers = mainResponse ? mainResponse.headers() : {};
    const blockedReason = detectBlocked(status, body, headers);

    return {
      body,
      responseUrl,
      status,
      headers,
      blockedReason,
      trace,
      runtimeEngine: "webview:playwright",
      timeoutMs
    };
  } finally {
    await browser.close();
  }
}

export function isBrowserUnavailableError(error) {
  const code = String(error?.code || "");
  const message = String(error?.message || error || "").toLowerCase();
  return (
    code === "ERR_MODULE_NOT_FOUND" ||
    message.includes("cannot find package 'playwright'") ||
    message.includes("executable doesn't exist") ||
    message.includes("please run the following command to download new browsers")
  );
}

export async function performWebViewRequest(request, options = {}) {
  const timeoutMs = Number(options.webViewTimeoutMs || appConfig.webViewTimeoutMs);
  try {
    return await performPlaywrightWebView(request, timeoutMs);
  } catch (error) {
    if (!isBrowserUnavailableError(error)) {
      throw error;
    }
    const fallback = await performFallbackWebView(request, timeoutMs);
    fallback.trace.push({
      type: "playwright_error",
      message: error?.message || String(error)
    });
    return fallback;
  }
}
