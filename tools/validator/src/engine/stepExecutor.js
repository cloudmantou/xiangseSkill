import { parseFieldValue } from "./fieldParser.js";
import { createDom, evaluateNodes } from "./xpath.js";
import { buildRequest } from "./requestBuilder.js";
import { performHttpRequest } from "../services/httpService.js";
import { performWebViewRequest } from "../services/webviewService.js";
import { getFixtureContent } from "../services/fixtureService.js";
import { runUserJs } from "./jsSandbox.js";
import { splitJsPipe } from "./template.js";

const RESERVED_KEYS = new Set([
  "actionID",
  "parserID",
  "responseFormatType",
  "validConfig",
  "requestInfo",
  "host",
  "httpHeaders",
  "list",
  "moreKeys",
  "JSParser",
  "requestJavascript",
  "responseJavascript",
  "requestFunction",
  "responseFunction",
  "nextPageUrl",
  "webView",
  "webViewJs",
  "webViewJsDelay",
  "webViewSkipUrls",
  "webViewSkipUrlsUnless",
  "webViewContentRules",
  "webViewSniff"
]);

const WEBVIEW_KEYS = [
  "webView",
  "webViewJs",
  "webViewJsDelay",
  "webViewSkipUrls",
  "webViewSkipUrlsUnless",
  "webViewContentRules",
  "webViewSniff"
];

function jsonPathGet(obj, pathExpr) {
  const clean = String(pathExpr || "").trim();
  if (!clean) {
    return obj;
  }

  const normalized = clean.replace(/^\$\.?/, "");
  const segments = normalized.includes("/")
    ? normalized.split("/").filter(Boolean)
    : normalized.split(".").filter(Boolean);

  let current = obj;
  for (const key of segments) {
    if (current == null) {
      return undefined;
    }
    current = current[key];
  }
  return current;
}

async function parseJsonField(expression, item, context) {
  const raw = String(expression || "").trim();
  if (!raw) {
    return "";
  }

  if (raw.startsWith("@js:")) {
    return runUserJs(raw.replace(/^@js:\s*/, ""), { ...context, result: item });
  }

  const pipe = splitJsPipe(raw);
  if (pipe) {
    const base = jsonPathGet(item, pipe.baseExpression);
    return runUserJs(pipe.jsCode, { ...context, result: base });
  }

  return jsonPathGet(item, raw);
}

function actionFields(actionConfig) {
  return Object.keys(actionConfig).filter((key) => !RESERVED_KEYS.has(key));
}

function hasNonEmpty(value) {
  if (value == null) return false;
  if (typeof value === "boolean") return value;
  if (typeof value === "number") return Number.isFinite(value) && value !== 0;
  if (typeof value === "string") return value.trim().length > 0;
  if (Array.isArray(value)) return value.length > 0;
  if (typeof value === "object") return Object.keys(value).length > 0;
  return false;
}

function hasWebViewSignal(action, request) {
  return WEBVIEW_KEYS.some((k) => hasNonEmpty(action?.[k]) || hasNonEmpty(request?.[k]));
}

function resolveRuntimeEngine(input, action, request) {
  const preferred = String(input?.engine || "auto").toLowerCase();
  if (preferred === "http" || preferred === "webview") {
    return preferred;
  }
  return hasWebViewSignal(action, request) ? "webview" : "http";
}

function collectWebViewAppliedKeys(action, request) {
  return WEBVIEW_KEYS.filter((k) => hasNonEmpty(action?.[k]) || hasNonEmpty(request?.[k]));
}

function canonicalFixtureUrl(value) {
  try {
    const url = new URL(String(value || "").trim());
    url.hash = "";
    return url.href;
  } catch {
    return "";
  }
}

function unsupportedDiagnostic(step, capability) {
  return {
    step,
    field: "unsupported",
    level: "error",
    message: `Unsupported Xiangse capability: ${capability}`
  };
}

function collectUnsupportedDiagnostics(step, action, request) {
  const capabilities = [];
  const parserID = String(action?.parserID || "DOM").trim().toUpperCase();
  const responseType = String(action?.responseFormatType || "html").trim().toLowerCase();

  if (parserID !== "DOM") {
    capabilities.push(`parserID=${parserID || "empty"}`);
  }
  if (!["html", "json"].includes(responseType)) {
    capabilities.push(`responseFormatType=${responseType || "empty"}`);
  }
  if (hasNonEmpty(action?.nextPageUrl) || Number(action?.moreKeys?.maxPage || 0) > 1) {
    capabilities.push("pagination");
  }
  if (hasNonEmpty(action?.webViewSniff) || hasNonEmpty(request?.webViewSniff)) {
    capabilities.push("webViewSniff");
  }
  if (hasNonEmpty(action?.webViewContentRules) || hasNonEmpty(request?.webViewContentRules)) {
    capabilities.push("webViewContentRules");
  }

  for (const key of [
    "JSParser",
    "requestJavascript",
    "responseJavascript",
    "requestFunction",
    "responseFunction"
  ]) {
    if (hasNonEmpty(action?.[key])) {
      capabilities.push(key);
    }
  }

  return [...new Set(capabilities)].map((capability) => unsupportedDiagnostic(step, capability));
}

export async function executeStep(input) {
  const startedAt = Date.now();
  const sourceEntry = input.source[input.sourceKey];
  if (!sourceEntry) {
    throw new Error(`sourceKey not found: ${input.sourceKey}`);
  }

  const action = sourceEntry[input.step];
  if (!action) {
    throw new Error(`Missing action: ${input.step}`);
  }

  const issues = [];
  const parseLimit = Math.max(1, Number(input.queryPayload?._parseLimit || 10));
  const request = await buildRequest({
    sourceConfig: sourceEntry,
    actionConfig: action,
    params: input.queryPayload,
    result: input.queryPayload?.result
  });
  issues.push(...collectUnsupportedDiagnostics(input.step, action, request));

  let body = "";
  let responseUrl = request.url;
  let fixtureUsed;
  let fixtureExpectedUrl = "";
  let fixtureUrlVerified = false;
  let status = 200;
  let blockedReason = "";
  let webviewTrace = [];
  let runtimeEngine = resolveRuntimeEngine(input, action, request);
  const webviewAppliedKeys = collectWebViewAppliedKeys(action, request);

  if (input.mode === "fixture") {
    const fixture = getFixtureContent(input.step, input.fixturesState);
    if (!fixture) {
      issues.push({
        step: input.step,
        field: "fixture",
        level: "error",
        message: "Fixture mode enabled but no fixture found"
      });
      body = "";
      status = 404;
    } else {
      body = fixture.content;
      fixtureUsed = fixture.used;
      fixtureExpectedUrl = String(fixture.expectedUrl || "").trim();
      if (fixtureExpectedUrl) {
        const expectedUrl = canonicalFixtureUrl(fixtureExpectedUrl);
        const actualUrl = canonicalFixtureUrl(request.url);
        fixtureUrlVerified = Boolean(expectedUrl && actualUrl && expectedUrl === actualUrl);
        if (!fixtureUrlVerified) {
          issues.push({
            step: input.step,
            field: "fixture_url",
            level: "error",
            message: `Fixture manifest URL does not match request URL: expected ${fixtureExpectedUrl}, actual ${request.url}`
          });
        }
      } else {
        issues.push({
          step: input.step,
          field: "fixture_url",
          level: "warning",
          message: "url_unverified: fixture has no manifest URL metadata"
        });
      }
      if (runtimeEngine === "webview") {
        webviewTrace.push({
          type: "fixture_replay",
          message: "fixture mode replay, webview runtime skipped"
        });
      }
    }
  } else {
    if (runtimeEngine === "webview") {
      const webviewRequest = input.performWebViewRequest || performWebViewRequest;
      const webviewResult = await webviewRequest(request, {
        webViewTimeoutMs: input.webViewTimeoutMs
      });
      body = webviewResult.body;
      responseUrl = webviewResult.responseUrl;
      status = webviewResult.status;
      blockedReason = webviewResult.blockedReason || "";
      webviewTrace = webviewResult.trace || [];
      runtimeEngine = webviewResult.runtimeEngine || runtimeEngine;
      if (runtimeEngine === "webview:fallback") {
        blockedReason =
          blockedReason ||
          "WebView runtime unavailable; HTTP + JSDOM fallback is incomplete evidence";
        issues.push({
          step: input.step,
          field: "webview",
          level: "error",
          message: "WebView fallback cannot satisfy live validation"
        });
      }
    } else {
      const httpResult = await performHttpRequest(request);
      body = httpResult.body;
      responseUrl = httpResult.responseUrl;
      status = httpResult.status;
      blockedReason = httpResult.blockedReason || "";
    }
    if (status >= 400) {
      issues.push({
        step: input.step,
        field: "http",
        level: "error",
        message: `HTTP status ${status}`
      });
    }
    if (blockedReason) {
      issues.push({
        step: input.step,
        field: "blocked",
        level: "error",
        message: blockedReason
      });
    }
  }

  const responseType = String(action.responseFormatType || "html").toLowerCase();
  const fields = actionFields(action);

  let listLengthOnlyDebug = 0;
  let list = [];
  let item = {};

  if (responseType === "json") {
    let jsonObj = null;
    try {
      jsonObj = JSON.parse(body || "{}");
    } catch (err) {
      issues.push({
        step: input.step,
        field: "response",
        level: "error",
        message: `Invalid JSON response: ${err?.message || "unknown"}`
      });
      jsonObj = {};
    }

    const listPath = String(action.list || "").trim();
    const ctx = {
      config: { ...sourceEntry, ...action },
      params: {
        ...input.queryPayload,
        responseUrl
      },
      result: null
    };

    if (listPath) {
      const rawList = jsonPathGet(jsonObj, listPath);
      const arr = Array.isArray(rawList) ? rawList : rawList ? [rawList] : [];
      listLengthOnlyDebug = arr.length;

      for (const rawItem of arr.slice(0, parseLimit)) {
        const parsed = {};
        for (const field of fields) {
          parsed[field] = await parseJsonField(String(action[field] || ""), rawItem, {
            ...ctx,
            result: rawItem
          });
        }
        list.push(parsed);
      }
    } else {
      for (const field of fields) {
        item[field] = await parseJsonField(String(action[field] || ""), jsonObj, {
          ...ctx,
          result: jsonObj
        });
      }
    }
  } else {
    const document = createDom(body || "");
    const listExpr = String(action.list || "").trim();

    if (listExpr) {
      const nodes = evaluateNodes(document, listExpr, document);
      listLengthOnlyDebug = nodes.length;
      for (const node of nodes.slice(0, parseLimit)) {
        const parsed = {};
        for (const field of fields) {
          parsed[field] = await parseFieldValue({
            document,
            expression: String(action[field] || ""),
            contextNode: node,
            context: {
              config: { ...sourceEntry, ...action },
              params: {
                ...input.queryPayload,
                responseUrl
              },
              result: null
            }
          });
        }
        list.push(parsed);
      }
    } else {
      for (const field of fields) {
        item[field] = await parseFieldValue({
          document,
          expression: String(action[field] || ""),
          contextNode: document,
          context: {
            config: { ...sourceEntry, ...action },
            params: {
              ...input.queryPayload,
              responseUrl
            },
            result: null
          }
        });
      }
    }
  }

  const elapsedMs = Date.now() - startedAt;
  return {
    step: input.step,
    success: !issues.some((issue) => issue.level === "error"),
    blocked: Boolean(blockedReason),
    blockedReason,
    requestDebug: {
      request,
      responseUrl,
      mode: input.mode,
      runtimeEngine,
      fixtureUsed,
      fixtureExpectedUrl,
      fixtureUrlVerified,
      status,
      blocked: Boolean(blockedReason),
      blockedReason,
      webviewTrace,
      webviewAppliedKeys
    },
    parseResult: {
      listLengthOnlyDebug,
      list,
      item
    },
    fieldDiagnostics: issues,
    elapsedMs
  };
}
