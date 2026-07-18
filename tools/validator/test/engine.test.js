import assert from "node:assert/strict";
import test from "node:test";

import { parseFieldValue } from "../src/engine/fieldParser.js";
import { executeStep } from "../src/engine/stepExecutor.js";
import { createDom, evaluateNodes, evaluateValue } from "../src/engine/xpath.js";
import { resolveWithHost } from "../src/utils/url.js";

test("list child XPath treats a leading // as relative to the current item", () => {
  const document = createDom(
    "<ul><li><a href='/a'>A</a></li><li><a href='/b'>B</a></li></ul>"
  );
  const items = evaluateNodes(document, "//li", document);

  assert.equal(evaluateValue(document, "//a/@href", items[0]), "/a");
  assert.equal(evaluateValue(document, "//a/@href", items[1]), "/b");
});

test("HTML field pipes accept whitespace between || and @js", async () => {
  const document = createDom("<p>value</p>");
  const value = await parseFieldValue({
    document,
    expression: "//missing || @js: return result || 'fallback';",
    contextNode: document,
    context: { config: {}, params: {}, result: null }
  });

  assert.equal(value, "fallback");
});

test("JSON field pipes accept whitespace between || and @js", async () => {
  const result = await executeStep({
    step: "bookDetail",
    source: {
      Source: {
        sourceUrl: "https://example.com",
        bookDetail: {
          requestInfo: "https://example.com/detail",
          responseFormatType: "json",
          title: "name || @js: return String(result) + '!';"
        }
      }
    },
    sourceKey: "Source",
    mode: "fixture",
    engine: "http",
    queryPayload: {},
    fixturesState: {
      mode: "map",
      data: { bookDetail: "{\"name\":\"Book\"}" }
    }
  });

  assert.equal(result.parseResult.item.title, "Book!");
});

test("URL resolution follows standard URL semantics", () => {
  assert.equal(
    resolveWithHost("https://example.com/base/index.html", "/chapter/1"),
    "https://example.com/chapter/1"
  );
  assert.equal(
    resolveWithHost("http://example.com/base/", "//cdn.example.com/a"),
    "http://cdn.example.com/a"
  );
  assert.equal(
    resolveWithHost("https://example.com/base/", "chapter/1"),
    "https://example.com/base/chapter/1"
  );
});

test("WebView HTTP fallback is blocked and reports the actual runtime", async () => {
  const result = await executeStep({
    step: "bookDetail",
    source: {
      Source: {
        sourceUrl: "https://example.com",
        bookDetail: {
          requestInfo: "https://example.com/detail",
          responseFormatType: "html",
          webView: true,
          title: "//h1/text()"
        }
      }
    },
    sourceKey: "Source",
    mode: "live",
    engine: "auto",
    queryPayload: {},
    performWebViewRequest: async () => ({
      body: "<h1>Book</h1>",
      responseUrl: "https://example.com/detail",
      status: 200,
      headers: {},
      blockedReason: "",
      trace: [{ type: "webview_engine_fallback" }],
      runtimeEngine: "webview:fallback"
    })
  });

  assert.equal(result.success, false);
  assert.equal(result.blocked, true);
  assert.equal(result.requestDebug.runtimeEngine, "webview:fallback");
  assert.ok(
    result.fieldDiagnostics.some(
      (diagnostic) =>
        diagnostic.field === "webview" &&
        diagnostic.level === "error" &&
        diagnostic.message.includes("fallback")
    )
  );
});

test("fixture request URL must match its manifest URL", async () => {
  const result = await executeStep({
    step: "bookDetail",
    source: {
      Source: {
        sourceUrl: "https://example.com",
        bookDetail: {
          requestInfo: "https://example.com/wrong",
          responseFormatType: "html",
          title: "//h1/text()"
        }
      }
    },
    sourceKey: "Source",
    mode: "fixture",
    engine: "http",
    queryPayload: {},
    fixturesState: {
      mode: "map",
      data: {
        bookDetail: {
          html: "<h1>Book</h1>",
          url: "https://example.com/detail"
        }
      }
    }
  });

  assert.equal(result.success, false);
  assert.equal(result.requestDebug.fixtureExpectedUrl, "https://example.com/detail");
  assert.equal(result.requestDebug.fixtureUrlVerified, false);
  assert.ok(
    result.fieldDiagnostics.some(
      (diagnostic) =>
        diagnostic.field === "fixture_url" &&
        diagnostic.level === "error" &&
        diagnostic.message.includes("does not match")
    )
  );
});

test("fixture without URL metadata is explicitly unverified", async () => {
  const result = await executeStep({
    step: "bookDetail",
    source: {
      Source: {
        sourceUrl: "https://example.com",
        bookDetail: {
          requestInfo: "https://example.com/detail",
          responseFormatType: "html",
          title: "//h1/text()"
        }
      }
    },
    sourceKey: "Source",
    mode: "fixture",
    engine: "http",
    queryPayload: {},
    fixturesState: {
      mode: "map",
      data: { bookDetail: "<h1>Book</h1>" }
    }
  });

  assert.equal(result.success, true);
  assert.equal(result.requestDebug.fixtureUrlVerified, false);
  assert.ok(
    result.fieldDiagnostics.some(
      (diagnostic) =>
        diagnostic.field === "fixture_url" &&
        diagnostic.level === "warning" &&
        diagnostic.message.includes("url_unverified")
    )
  );
});

for (const unsupportedCase of [
  {
    name: "parserID=JS",
    action: { parserID: "JS" },
    capability: "parserID=JS"
  },
  {
    name: "pagination",
    action: { nextPageUrl: "//a/@href", moreKeys: { maxPage: 2 } },
    capability: "pagination"
  },
  {
    name: "special response format",
    action: { responseFormatType: "data" },
    capability: "responseFormatType=data"
  },
  {
    name: "WebView sniff",
    action: { webViewSniff: true },
    capability: "webViewSniff"
  }
]) {
  test(`unsupported ${unsupportedCase.name} produces a structured error`, async () => {
    const result = await executeStep({
      step: "bookDetail",
      source: {
        Source: {
          sourceUrl: "https://example.com",
          bookDetail: {
            requestInfo: "https://example.com/detail",
            responseFormatType: "html",
            title: "//h1",
            ...unsupportedCase.action
          }
        }
      },
      sourceKey: "Source",
      mode: "fixture",
      engine: "http",
      queryPayload: {},
      fixturesState: {
        mode: "map",
        data: { bookDetail: "<h1>Book</h1>" }
      }
    });

    assert.equal(result.success, false);
    assert.ok(
      result.fieldDiagnostics.some(
        (diagnostic) =>
          diagnostic.field === "unsupported" &&
          diagnostic.level === "error" &&
          diagnostic.message.includes(unsupportedCase.capability)
      )
    );
  });
}
