/**
 * StandarReader 2.56.1 dynamic trace (Frida)
 *
 * Usage (USB device, app running):
 *   frida -U -n StandarReader -l tools/scripts/frida_dommodel_trace.js
 *   frida -U -f com.appbox.StandarReader -l tools/scripts/frida_dommodel_trace.js --no-pause
 *
 * Targets:
 * - DomModelParser.getRequestInfoForConfig:parserParams:error:
 * - DomModelParser.valueForNode:config:rule:ruleKey:userInfo:removeHtml:
 * - BookQueryManager.queryByActionID:book:queryInfo:sourceName:userInfo:target:notify:cachePolicy:
 */

function safeStr(v, max) {
  if (v === null || v === undefined) return String(v);
  var s = String(v);
  return s.length > max ? s.slice(0, max) + "..." : s;
}

function hookObjcMethod(className, selector, onEnter, onLeave) {
  if (!ObjC.available) {
    console.log("[!] ObjC runtime unavailable");
    return;
  }
  var cls = ObjC.classes[className];
  if (!cls) {
    console.log("[!] class not found: " + className);
    return;
  }
  var m = cls[selector];
  if (!m) {
    console.log("[!] method not found: " + className + " " + selector);
    return;
  }
  Interceptor.attach(m.implementation, {
    onEnter: function (args) {
      this.ts = Date.now();
      if (onEnter) onEnter.call(this, args);
    },
    onLeave: function (retval) {
      if (onLeave) onLeave.call(this, retval, Date.now() - this.ts);
    }
  });
  console.log("[+] hooked " + className + " " + selector);
}

if (ObjC.available) {
  hookObjcMethod(
    "DomModelParser",
    "- getRequestInfoForConfig:parserParams:error:",
    function (args) {
      var config = new ObjC.Object(args[2]);
      var params = new ObjC.Object(args[3]);
      console.log("\n[DomModelParser.getRequestInfo]");
      console.log("  config: " + safeStr(config.toString(), 500));
      console.log("  params: " + safeStr(params.toString(), 500));
    },
    function (retval, ms) {
      var out = retval.isNull() ? "null" : new ObjC.Object(retval).toString();
      console.log("  return(" + ms + "ms): " + safeStr(out, 800));
    }
  );

  hookObjcMethod(
    "DomModelParser",
    "- valueForNode:config:rule:ruleKey:userInfo:removeHtml:",
    function (args) {
      var ruleKey = new ObjC.Object(args[5]).toString();
      var rule = new ObjC.Object(args[4]).toString();
      console.log("\n[DomModelParser.valueForNode] key=" + ruleKey);
      console.log("  rule: " + safeStr(rule, 300));
    },
    function (retval, ms) {
      var out = retval.isNull() ? "null" : new ObjC.Object(retval).toString();
      console.log("  value(" + ms + "ms): " + safeStr(out, 400));
    }
  );

  hookObjcMethod(
    "BookQueryManager",
    "- queryByActionID:book:queryInfo:sourceName:userInfo:target:notify:cachePolicy:",
    function (args) {
      var actionID = new ObjC.Object(args[2]).toString();
      var sourceName = new ObjC.Object(args[5]).toString();
      console.log("\n[BookQueryManager.queryByActionID] action=" + actionID + " source=" + sourceName);
    }
  );
} else {
  console.log("ObjC runtime not available in this process.");
}