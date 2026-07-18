import fs from "node:fs";
import path from "node:path";

const STEP_NAMES = ["searchBook", "bookDetail", "chapterList", "chapterContent"];

function fixtureMap(value, label) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${label} must contain a JSON object`);
  }
  return value;
}

function loadFixtureMapFromJson(filePath) {
  const raw = fs.readFileSync(filePath, "utf8");
  return fixtureMap(JSON.parse(raw), `Fixtures file ${filePath}`);
}

function resolveFixtureFileFromDir(dirPath, step) {
  const candidates = [
    `${step}.html`,
    `${step}.json`,
    `${step}.txt`,
    `${step}.response`,
    `${step}.resp`
  ];
  for (const name of candidates) {
    const full = path.join(dirPath, name);
    if (fs.existsSync(full) && fs.statSync(full).isFile()) {
      return full;
    }
  }
  return "";
}

function resolveMapEntry(map, step) {
  const entry = map?.[step];
  if (!entry) return null;
  if (typeof entry === "string") {
    if (fs.existsSync(entry) && fs.statSync(entry).isFile()) {
      return { content: fs.readFileSync(entry, "utf8"), used: entry };
    }
    return { content: entry, used: "inline" };
  }
  if (typeof entry === "object") {
    const expectedUrl = typeof entry.url === "string" ? entry.url.trim() : "";
    const urlMetadata = expectedUrl ? { expectedUrl } : {};
    if (entry.html) {
      return { content: String(entry.html), used: "inline", ...urlMetadata };
    }
    if (entry.file && fs.existsSync(entry.file) && fs.statSync(entry.file).isFile()) {
      return {
        content: fs.readFileSync(entry.file, "utf8"),
        used: entry.file,
        ...urlMetadata
      };
    }
  }
  return null;
}

export function normalizeFixturesInput(fixturesInput) {
  const raw = String(fixturesInput || "").trim();
  if (!raw) return { mode: "none", data: {} };

  if (raw.startsWith("{")) {
    try {
      return { mode: "map", data: fixtureMap(JSON.parse(raw), "Fixtures JSON") };
    } catch (error) {
      throw new Error(`Invalid fixtures JSON: ${error?.message || String(error)}`);
    }
  }

  if (!fs.existsSync(raw)) {
    throw new Error(`Fixtures path not found: ${raw}`);
  }

  const stat = fs.statSync(raw);
  if (stat.isFile()) {
    if (raw.toLowerCase().endsWith(".json")) {
      return { mode: "map", data: loadFixtureMapFromJson(raw) };
    }
    return { mode: "single", data: { __all__: raw } };
  }

  if (stat.isDirectory()) {
    const map = {};
    const manifestPath = path.join(raw, "manifest.json");
    const manifest = fs.existsSync(manifestPath)
      ? loadFixtureMapFromJson(manifestPath)
      : {};
    for (const step of STEP_NAMES) {
      const f = resolveFixtureFileFromDir(raw, step);
      if (f) {
        const manifestEntry = manifest?.[step];
        const expectedUrl =
          manifestEntry && typeof manifestEntry === "object"
            ? String(manifestEntry.url || "").trim()
            : "";
        map[step] = { file: f, url: expectedUrl };
      }
    }
    return { mode: "dir", data: map };
  }

  return { mode: "none", data: {} };
}

export function getFixtureContent(step, fixturesState) {
  if (!fixturesState || fixturesState.mode === "none") return null;

  if (fixturesState.mode === "single") {
    const file = fixturesState.data.__all__;
    return { content: fs.readFileSync(file, "utf8"), used: file };
  }

  if (fixturesState.mode === "map" || fixturesState.mode === "dir") {
    const resolved = resolveMapEntry(fixturesState.data, step);
    if (resolved) return resolved;
    const filePath = fixturesState.data?.[step];
    if (typeof filePath === "string" && fs.existsSync(filePath) && fs.statSync(filePath).isFile()) {
      return { content: fs.readFileSync(filePath, "utf8"), used: filePath };
    }
  }

  return null;
}
