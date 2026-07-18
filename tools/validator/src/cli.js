import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { normalizeFixturesInput } from "./services/fixtureService.js";
import { runFullValidation } from "./services/validationService.js";

function parseArgs(argv) {
  const args = { _: [] };
  for (let i = 0; i < argv.length; i += 1) {
    const token = argv[i];
    if (!token.startsWith("--")) {
      args._.push(token);
      continue;
    }
    const key = token.slice(2);
    const next = argv[i + 1];
    if (!next || next.startsWith("--")) {
      args[key] = true;
    } else {
      args[key] = next;
      i += 1;
    }
  }
  return args;
}

function looksLikeSourceEntry(value) {
  return Boolean(
    value &&
      typeof value === "object" &&
      (value.searchBook || value.bookDetail || value.chapterList || value.chapterContent)
  );
}

function normalizeMap(inputObj) {
  if (!inputObj || typeof inputObj !== "object" || Array.isArray(inputObj)) {
    throw new Error("Invalid source JSON: expected object");
  }

  if (looksLikeSourceEntry(inputObj)) {
    const name = String(inputObj.sourceName || "ImportedSource");
    return {
      [name]: inputObj
    };
  }

  const keys = Object.keys(inputObj);
  if (keys.length === 0) {
    throw new Error("Invalid source JSON: empty object");
  }

  return inputObj;
}

function readJson(filePath) {
  const text = fs.readFileSync(filePath, "utf8");
  return JSON.parse(text);
}

function resolveSourceKey(sourceMap, preferredKey) {
  const keys = Object.keys(sourceMap);
  if (keys.length === 0) {
    throw new Error("No source entries found");
  }
  if (preferredKey) {
    if (!sourceMap[preferredKey]) {
      throw new Error(`sourceKey not found: ${preferredKey}`);
    }
    return preferredKey;
  }
  return keys[0];
}

function toInt(value, fallback) {
  const n = Number(value);
  if (Number.isFinite(n)) return Math.trunc(n);
  return fallback;
}

function usage() {
  return `xiangse-validator CLI\n\nUsage:\n  node src/cli.js run --input <source.json> [--source-key <name>] [--mode live|fixture] [--engine auto|http|webview] [--webview-timeout 25] [--keyword 都市] [--page-index 1] [--offset 0] [--book-index 0] [--chapter-index 0] [--min-content-length 50] [--fixtures <dir|json|map-json-string>] [--output <report.json>]\n`;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const command = args._[0];

  if (!command || command === "-h" || command === "--help") {
    process.stdout.write(usage());
    return;
  }

  if (command !== "run") {
    throw new Error(`Unsupported command: ${command}`);
  }

  const input = String(args.input || "").trim();
  if (!input) {
    throw new Error("--input is required");
  }

  const inputPath = path.resolve(input);
  if (!fs.existsSync(inputPath)) {
    throw new Error(`input not found: ${inputPath}`);
  }

  const sourceRaw = readJson(inputPath);
  const source = normalizeMap(sourceRaw);
  const sourceKey = resolveSourceKey(source, args["source-key"] ? String(args["source-key"]) : "");

  const mode = String(args.mode || "live").toLowerCase();
  if (mode !== "live" && mode !== "fixture") {
    throw new Error(`invalid mode: ${mode}`);
  }
  const engine = String(args.engine || "auto").toLowerCase();
  if (!["auto", "http", "webview"].includes(engine)) {
    throw new Error(`invalid engine: ${engine}`);
  }

  const fixturesState = normalizeFixturesInput(args.fixtures ? String(args.fixtures) : "");

  const result = await runFullValidation({
    source,
    sourceKey,
    testConfig: {
      keyword: String(args.keyword || "都市"),
      pageIndex: toInt(args["page-index"], 1),
      offset: toInt(args.offset, 0),
      bookPickIndex: toInt(args["book-index"], 0),
      chapterPickIndex: toInt(args["chapter-index"], 0),
      mode,
      engine,
      fixturesState,
      minContentLength: toInt(args["min-content-length"], 50),
      webViewTimeoutSeconds: toInt(args["webview-timeout"], 25)
    }
  });

  const output = {
    ok: result.report.success,
    input: inputPath,
    sourceKey,
    mode,
    engine,
    report: result.report
  };

  const outputText = JSON.stringify(output, null, 2);
  if (args.output) {
    const outPath = path.resolve(String(args.output));
    fs.mkdirSync(path.dirname(outPath), { recursive: true });
    fs.writeFileSync(outPath, outputText, "utf8");
  }

  process.stdout.write(`${outputText}\n`);
  if (!result.report.success) {
    process.exitCode = result.report.verdict.status === "blocked" ? 2 : 1;
  }
}

main().catch((error) => {
  const payload = {
    ok: false,
    error: error?.message || String(error)
  };
  process.stderr.write(`${JSON.stringify(payload, null, 2)}\n`);
  process.exit(1);
});
