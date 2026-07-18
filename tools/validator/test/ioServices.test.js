import assert from "node:assert/strict";
import fs from "node:fs";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import {
  getFixtureContent,
  normalizeFixturesInput
} from "../src/services/fixtureService.js";
import { performHttpRequest } from "../src/services/httpService.js";

function listen(server) {
  return new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
}

function close(server) {
  return new Promise((resolve, reject) => {
    server.close((error) => (error ? reject(error) : resolve()));
  });
}

test("fixture service loads inline maps, JSON maps, files, and directories", () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "xiangse-fixtures-"));
  try {
    const responseFile = path.join(directory, "response.txt");
    fs.writeFileSync(responseFile, "from-file", "utf8");

    const inline = normalizeFixturesInput(
      JSON.stringify({
        searchBook: "inline-body",
        bookDetail: { html: "<h1>inline-html</h1>" },
        chapterList: { file: responseFile }
      })
    );
    assert.deepEqual(getFixtureContent("searchBook", inline), {
      content: "inline-body",
      used: "inline"
    });
    assert.deepEqual(getFixtureContent("bookDetail", inline), {
      content: "<h1>inline-html</h1>",
      used: "inline"
    });
    assert.deepEqual(getFixtureContent("chapterList", inline), {
      content: "from-file",
      used: responseFile
    });

    const mapFile = path.join(directory, "fixtures.json");
    fs.writeFileSync(mapFile, JSON.stringify({ chapterContent: "mapped" }), "utf8");
    const mapState = normalizeFixturesInput(mapFile);
    assert.equal(getFixtureContent("chapterContent", mapState).content, "mapped");

    const singleState = normalizeFixturesInput(responseFile);
    assert.equal(getFixtureContent("searchBook", singleState).content, "from-file");

    fs.writeFileSync(path.join(directory, "searchBook.html"), "directory-body", "utf8");
    fs.writeFileSync(
      path.join(directory, "manifest.json"),
      JSON.stringify({ searchBook: { url: "https://example.com/search?q=book" } }),
      "utf8"
    );
    const directoryState = normalizeFixturesInput(directory);
    assert.equal(getFixtureContent("searchBook", directoryState).content, "directory-body");
    assert.equal(
      getFixtureContent("searchBook", directoryState).expectedUrl,
      "https://example.com/search?q=book"
    );
    assert.equal(getFixtureContent("bookDetail", directoryState), null);
    assert.equal(getFixtureContent("searchBook", { mode: "none", data: {} }), null);
  } finally {
    fs.rmSync(directory, { recursive: true, force: true });
  }
});

test("fixture service rejects a non-object JSON map file", () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "xiangse-fixtures-"));
  try {
    const mapFile = path.join(directory, "fixtures.json");
    fs.writeFileSync(mapFile, "[1,2,3]", "utf8");
    assert.throws(() => normalizeFixturesInput(mapFile), /must contain a JSON object/);
  } finally {
    fs.rmSync(directory, { recursive: true, force: true });
  }
});

test("HTTP service sends GET and form POST requests and classifies blocked responses", async () => {
  const seen = [];
  const server = http.createServer((request, response) => {
    let body = "";
    request.on("data", (chunk) => {
      body += chunk;
    });
    request.on("end", () => {
      seen.push({ url: request.url, method: request.method, body, headers: request.headers });
      if (request.url.startsWith("/rate")) {
        response.writeHead(429);
        response.end("slow down");
        return;
      }
      if (request.url.startsWith("/forbidden")) {
        response.writeHead(403);
        response.end("Cloudflare challenge");
        return;
      }
      if (request.url.startsWith("/middleware")) {
        response.writeHead(200, { "cf-mitigated": "challenge" });
        response.end("middleware");
        return;
      }
      response.writeHead(200, { "content-type": "text/plain" });
      response.end("ok");
    });
  });
  await listen(server);

  try {
    const host = `http://127.0.0.1:${server.address().port}`;
    const getResult = await performHttpRequest({
      url: `${host}/get`,
      method: "GET",
      httpParams: { q: "book" },
      httpHeaders: { "X-Test": "get" }
    });
    assert.equal(getResult.status, 200);
    assert.equal(getResult.body, "ok");
    assert.match(seen[0].url, /q=book/);

    const postResult = await performHttpRequest({
      url: `${host}/post`,
      method: "POST",
      httpParams: { q: "book", page: 2 },
      httpHeaders: { "X-Test": "post" }
    });
    assert.equal(postResult.status, 200);
    assert.match(seen[1].body, /q=book/);
    assert.match(seen[1].headers["content-type"], /application\/x-www-form-urlencoded/);

    assert.equal(
      (await performHttpRequest({ url: `${host}/rate`, method: "GET" })).blockedReason,
      "HTTP 429 rate limited"
    );
    assert.equal(
      (await performHttpRequest({ url: `${host}/forbidden`, method: "GET" })).blockedReason,
      "HTTP 403 blocked by anti-bot challenge"
    );
    assert.equal(
      (await performHttpRequest({ url: `${host}/middleware`, method: "GET" })).blockedReason,
      "Blocked by challenge middleware (cf-mitigated)"
    );
  } finally {
    await close(server);
  }
});
