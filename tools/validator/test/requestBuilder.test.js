import assert from "node:assert/strict";
import test from "node:test";

import { buildRequest } from "../src/engine/requestBuilder.js";

test("buildRequest applies templates, merged headers, and action WebView options", async () => {
  const request = await buildRequest({
    sourceConfig: {
      sourceUrl: "https://example.com/base/",
      httpHeaders: { Source: "yes", Shared: "source" }
    },
    actionConfig: {
      requestInfo: "/search?q=%@keyWord&page=%@pageIndex",
      httpHeaders: { Action: "yes", Shared: "action" },
      webView: "true",
      webViewJsDelay: "2",
      webViewSkipUrls: "ads, tracker\nmetrics"
    },
    params: { keyWord: "都市", pageIndex: 3 }
  });

  assert.equal(request.url, "https://example.com/search?q=%E9%83%BD%E5%B8%82&page=3");
  assert.equal(request.method, "GET");
  assert.deepEqual(request.httpHeaders, {
    Source: "yes",
    Shared: "action",
    Action: "yes"
  });
  assert.equal(request.webView, true);
  assert.equal(request.webViewJsDelay, 2);
  assert.deepEqual(request.webViewSkipUrls, ["ads", "tracker", "metrics"]);
});

test("buildRequest supports JavaScript string and object results", async () => {
  const stringRequest = await buildRequest({
    sourceConfig: { sourceUrl: "https://example.com" },
    actionConfig: { requestInfo: "@js: return '/detail/' + params.id;" },
    params: { id: 7 }
  });
  assert.equal(stringRequest.url, "https://example.com/detail/7");
  assert.equal(stringRequest.method, "GET");

  const objectRequest = await buildRequest({
    sourceConfig: {
      sourceUrl: "https://example.com",
      httpHeaders: { Base: "yes" }
    },
    actionConfig: {
      requestInfo:
        "@js: return { url: '/submit', POST: true, httpParams: { q: params.q }, " +
        "httpHeaders: { Extra: 'yes' }, webView: true, webViewSkipUrlsUnless: 'allow' };"
    },
    params: { q: "book" }
  });
  assert.equal(objectRequest.url, "https://example.com/submit");
  assert.equal(objectRequest.method, "POST");
  assert.deepEqual(objectRequest.httpParams, { q: "book" });
  assert.deepEqual(objectRequest.httpHeaders, { Base: "yes", Extra: "yes" });
  assert.equal(objectRequest.webView, true);
  assert.deepEqual(objectRequest.webViewSkipUrlsUnless, ["allow"]);
});

test("buildRequest supports object requestInfo and rejects invalid forms", async () => {
  const request = await buildRequest({
    sourceConfig: { sourceUrl: "https://example.com", httpHeaders: { A: "1" } },
    actionConfig: {
      requestInfo: {
        url: "/api",
        POST: true,
        httpParams: { page: 2 },
        httpHeaders: { B: "2" },
        webView: false
      }
    },
    params: {}
  });
  assert.equal(request.url, "https://example.com/api");
  assert.equal(request.method, "POST");
  assert.deepEqual(request.httpParams, { page: 2 });
  assert.deepEqual(request.httpHeaders, { A: "1", B: "2" });
  assert.equal(request.webView, false);

  await assert.rejects(
    buildRequest({ sourceConfig: {}, actionConfig: {}, params: {} }),
    /requestInfo is required/
  );
  await assert.rejects(
    buildRequest({ sourceConfig: {}, actionConfig: { requestInfo: 42 }, params: {} }),
    /Unsupported requestInfo type/
  );
});
