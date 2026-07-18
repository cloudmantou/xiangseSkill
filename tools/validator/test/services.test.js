import assert from "node:assert/strict";
import http from "node:http";
import test from "node:test";

import { normalizeFixturesInput } from "../src/services/fixtureService.js";
import { runFullValidation } from "../src/services/validationService.js";
import { performWebViewRequest } from "../src/services/webviewService.js";

function listen(server) {
  return new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
}

function close(server) {
  return new Promise((resolve, reject) => {
    server.close((error) => (error ? reject(error) : resolve()));
  });
}

function makeFourStepSource(host) {
  return {
    Source: {
      sourceUrl: host,
      searchBook: {
        requestInfo: host,
        responseFormatType: "html",
        list: "//book",
        bookName: "a",
        detailUrl: "a/@href"
      },
      bookDetail: {
        requestInfo: host,
        responseFormatType: "html",
        title: "//title"
      },
      chapterList: {
        requestInfo: host,
        responseFormatType: "html",
        list: "//chapter",
        title: "text()",
        url: "@href"
      },
      chapterContent: {
        requestInfo: host,
        responseFormatType: "html",
        content: "//content"
      }
    }
  };
}

test("HTTP 500 responses cannot produce a passing validation", async () => {
  const html =
    "<title>Book</title><book><a href='/detail'>Book</a></book>" +
    "<chapter href='/chapter/1'>Chapter</chapter>" +
    "<content>abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789正文足够长</content>";
  const server = http.createServer((_request, response) => {
    response.writeHead(500, { "content-type": "text/html" });
    response.end(html);
  });
  await listen(server);

  try {
    const host = `http://127.0.0.1:${server.address().port}`;
    const { report } = await runFullValidation({
      source: makeFourStepSource(host),
      sourceKey: "Source",
      testConfig: { mode: "live", engine: "http", minContentLength: 50 }
    });

    assert.equal(report.success, false);
    assert.equal(report.verdict.status, "fail");
    assert.ok(report.verdict.failReasons.some((reason) => reason.includes("HTTP status 500")));
  } finally {
    await close(server);
  }
});

test("explicit invalid fixtures fail fast", () => {
  assert.throws(() => normalizeFixturesInput("{not-json"), /Invalid fixtures JSON/);
  assert.throws(
    () => normalizeFixturesInput("/definitely/missing/xiangse-fixtures"),
    /Fixtures path not found/
  );
});

test(
  "WebView JavaScript errors propagate instead of being converted to a successful response",
  { timeout: 15_000 },
  async () => {
    const server = http.createServer((_request, response) => {
      response.writeHead(200, { "content-type": "text/html" });
      response.end("<html><body>static content</body></html>");
    });
    await listen(server);

    try {
      const url = `http://127.0.0.1:${server.address().port}/`;
      await assert.rejects(
        performWebViewRequest(
          {
            url,
            method: "GET",
            httpHeaders: {},
            webView: true,
            webViewJs: "throw new Error('boom')"
          },
          { webViewTimeoutMs: 3_000 }
        ),
        /boom/
      );
    } finally {
      await close(server);
    }
  }
);
