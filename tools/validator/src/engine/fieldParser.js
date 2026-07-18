import { isJsRule, splitJsPipe, unwrapJsRule } from "./template.js";
import { runUserJs } from "./jsSandbox.js";
import { evaluateValue } from "./xpath.js";

export async function parseFieldValue(input) {
  const { document, expression, contextNode, context } = input;
  const raw = String(expression || "").trim();
  if (!raw) {
    return "";
  }

  if (isJsRule(raw)) {
    return runUserJs(unwrapJsRule(raw), context);
  }

  const pipe = splitJsPipe(raw);
  if (pipe) {
    const baseValue = pipe.baseExpression
      ? evaluateValue(document, pipe.baseExpression, contextNode)
      : context.result;
    return runUserJs(pipe.jsCode, { ...context, result: baseValue });
  }

  return evaluateValue(document, raw, contextNode);
}
