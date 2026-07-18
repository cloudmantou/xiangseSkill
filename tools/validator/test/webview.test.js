import assert from "node:assert/strict";
import http from "node:http";
import test from "node:test";

import {
  isBrowserUnavailableError,
  performWebViewRequest
} from "../src/services/webviewService.js";

function listen(server) {
  return new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
}

function close(server) {
  return new Promise((resolve, reject) => {
    server.close((error) => (error ? reject(error) : resolve()));
  });
}

test("browser-unavailable detection is narrow", () => {
  assert.equal(isBrowserUnavailableError({ code: "ERR_MODULE_NOT_FOUND" }), true);
  assert.equal(
    isBrowserUnavailableError(new Error("browserType.launch: Executable doesn't exist")),
    true
  );
  assert.equal(isBrowserUnavailableError(new Error("page.goto: Timeout 100ms exceeded")), false);
  assert.equal(isBrowserUnavailableError(new Error("boom")), false);
});

test(
  "Playwright WebView applies skip rules and JavaScript",
  { timeout: 15_000 },
  async () => {
    const server = http.createServer((request, response) => {
      if (request.url === "/skip.png") {
        response.writeHead(200, { "content-type": "image/png" });
        response.end("image");
        return;
      }
      response.writeHead(200, { "content-type": "text/html" });
      response.end("<html><body><img src='/skip.png'><main>ready</main></body></html>");
    });
    await listen(server);

    try {
      const url = `http://127.0.0.1:${server.address().port}/`;
      const result = await performWebViewRequest(
        {
          url,
          method: "GET",
          httpHeaders: {},
          webView: true,
          webViewSkipUrls: ["skip.png"],
          webViewJs: "document.body.setAttribute('data-tested', 'yes')"
        },
        { webViewTimeoutMs: 3_000 }
      );

      assert.equal(result.runtimeEngine, "webview:playwright");
      assert.equal(result.status, 200);
      assert.match(result.body, /data-tested="yes"/);
      assert.ok(result.trace.some((entry) => entry.type === "skip_url"));
      assert.ok(result.trace.some((entry) => entry.type === "webview_js_eval" && entry.ok));
    } finally {
      await close(server);
    }
  }
);

test("Playwright WebView waits for POST navigation and reports its status", { timeout: 15_000 }, async () => {
  const server = http.createServer((request, response) => {
    let body = "";
    request.on("data", (chunk) => {
      body += chunk;
    });
    request.on("end", () => {
      response.writeHead(201, { "content-type": "text/html" });
      response.end(`<html><body>${request.method}:${body}</body></html>`);
    });
  });
  await listen(server);

  try {
    const url = `http://127.0.0.1:${server.address().port}/submit`;
    const result = await performWebViewRequest(
      {
        url,
        method: "POST",
        httpParams: { q: "book" },
        httpHeaders: {},
        webView: true
      },
      { webViewTimeoutMs: 3_000 }
    );

    assert.equal(result.runtimeEngine, "webview:playwright");
    assert.equal(result.status, 201);
    assert.match(result.body, /POST:q=book/);
  } finally {
    await close(server);
  }
});
