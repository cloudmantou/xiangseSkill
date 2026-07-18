export function isAbsoluteUrl(input) {
  return /^https?:\/\//i.test(String(input || ""));
}

export function resolveWithHost(host, input) {
  const cleaned = String(input || "").trim();
  if (!cleaned) {
    return "";
  }
  if (isAbsoluteUrl(cleaned)) {
    return new URL(cleaned).toString();
  }

  return new URL(cleaned, String(host || "").trim()).toString();
}

export function canResolveAgainstHost(host, maybeRelative) {
  try {
    resolveWithHost(host, maybeRelative);
    return true;
  } catch {
    return false;
  }
}
