import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";

const cliPath = new URL("../src/cli.js", import.meta.url);

function writeSource(directory) {
  const sourcePath = path.join(directory, "source.json");
  const action = (body) => ({
    requestInfo: "https://example.com",
    responseFormatType: "html",
    ...body
  });
  const source = {
    Source: {
      sourceUrl: "https://example.com",
      searchBook: action({ list: "//book", bookName: "a", detailUrl: "a/@href" }),
      bookDetail: action({ title: "//title" }),
      chapterList: action({ list: "//chapter", title: "text()", url: "@href" }),
      chapterContent: action({ content: "//content" })
    }
  };
  fs.writeFileSync(sourcePath, JSON.stringify(source), "utf8");
  return sourcePath;
}

test("CLI aligns top-level ok and exit code with a failed report", () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "xiangse-validator-cli-"));
  try {
    const sourcePath = writeSource(directory);
    const fixtures = JSON.stringify({
      searchBook: "<book><a href='/detail'>Book</a></book>",
      bookDetail: "<title>Book</title>",
      chapterList: "<chapter href='/chapter/1'>Chapter</chapter>",
      chapterContent: "<content>short</content>"
    });
    const result = spawnSync(
      process.execPath,
      [
        cliPath.pathname,
        "run",
        "--input",
        sourcePath,
        "--source-key",
        "Source",
        "--mode",
        "fixture",
        "--fixtures",
        fixtures,
        "--min-content-length",
        "100"
      ],
      { encoding: "utf8" }
    );

    assert.equal(result.status, 1);
    const output = JSON.parse(result.stdout);
    assert.equal(output.ok, false);
    assert.equal(output.report.success, false);
    assert.equal(output.report.verdict.status, "fail");
  } finally {
    fs.rmSync(directory, { recursive: true, force: true });
  }
});

test("CLI rejects an explicitly missing fixtures path", () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "xiangse-validator-cli-"));
  try {
    const sourcePath = writeSource(directory);
    const result = spawnSync(
      process.execPath,
      [
        cliPath.pathname,
        "run",
        "--input",
        sourcePath,
        "--mode",
        "fixture",
        "--fixtures",
        path.join(directory, "missing")
      ],
      { encoding: "utf8" }
    );

    assert.equal(result.status, 1);
    assert.equal(result.stdout, "");
    assert.match(JSON.parse(result.stderr).error, /Fixtures path not found/);
  } finally {
    fs.rmSync(directory, { recursive: true, force: true });
  }
});
