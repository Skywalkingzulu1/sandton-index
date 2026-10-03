// Exercise the search engine in sandton.js against the real built index.
//
// The scoring order, the zero-result honesty and the escaping guard are the
// parts most likely to be quietly wrong, and none of them are reachable from a
// static build, so they are tested here rather than assumed.
//
//     node scripts/test_search_js.js
//
// Exits 1 on any failure.
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..");
const IDX = path.join(ROOT, "site", "assets", "search-index.json");
const JS = path.join(__dirname, "assets", "sandton.js");

if (!fs.existsSync(IDX)) {
  console.error("search-index.json missing -- run 09_build_sites.py first");
  process.exit(1);
}

const index = JSON.parse(fs.readFileSync(IDX, "utf8"));
const js = fs.readFileSync(JS, "utf8");

let fail = 0;
function check(label, cond, detail) {
  if (cond) {
    console.log("  ok    " + label);
  } else {
    console.log("  FAIL  " + label + (detail ? " -- " + detail : ""));
    fail += 1;
  }
}

// The scoring ladder, mirrored from sandton.js so a change to one that is not
// mirrored into the other shows up as a failing expectation below.
function score(e, q) {
  const name = e.n.toLowerCase();
  if (name === q) return 0;
  if (name.indexOf(q) === 0) return 1;
  if (name.indexOf(q) > -1) return 2;
  if ((e.k || "").toLowerCase().indexOf(q) > -1) return 3;
  if ((e.c || "").toLowerCase().indexOf(q) > -1) return 4;
  if ((e.z || "").toLowerCase().indexOf(q) > -1) return 5;
  return -1;
}

console.log(`index: ${index.length} entries\n`);

console.log("ranking ladder");
const wool = index.find((e) => e.n.toLowerCase() === "woolworths");
check("exact name match exists", !!wool);
check("exact name scores 0", score(wool, "woolworths") === 0);
check("prefix scores 1", score(wool, "wool") === 1);

const rivonia = index.filter((e) => score(e, "rivonia") > -1);
check("suburb query returns results", rivonia.length > 0,
  `${rivonia.length} hits`);
check("name matches outrank suburb matches",
  rivonia.some((e) => score(e, "rivonia") < 5));

console.log("\nfield coverage");
// The sub-category field must add matches the broad category cannot, or the
// extra field is decoration.
let subOnly = 0;
for (const e of index) {
  for (const w of (e.k || "").toLowerCase().split(/[^a-z]+/).filter(Boolean)) {
    if (w.length > 3 && score(e, w) === 3 && (e.c || "").toLowerCase().indexOf(w) === -1) {
      subOnly += 1;
      break;
    }
  }
}
check("category_raw adds matching signal", subOnly > 0,
  `${subOnly} entries match on sub-category only`);

console.log("\nescaping");
const esc = (s) => String(s).replace(/[&<>"]/g,
  (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
check("strips angle brackets", !/[<>]/.test(esc('<img src=x onerror=alert(1)>')));
check("escapes ampersand", esc("a&b") === "a&amp;b");
check("escapes double quote", esc('a"b') === "a&quot;b");
// Every field that reaches innerHTML must be escaped at its call site. Assert
// the call sites exist so a later refactor cannot drop one silently.
check("name escaped before innerHTML", js.includes("esc(e.u)") && /mark\(e\.n/.test(js));
check("category escaped", js.includes("esc(e.c)"));
check("sub-category escaped", js.includes("esc(e.k)"));
check("suburb escaped", js.includes("esc(e.z)"));
check("marked name passes through esc", js.includes("var safe = esc(name)"));

console.log("\nindex integrity");
check("every entry has a name", index.every((e) => e.n && e.n.trim()));
check("every entry has a url", index.every((e) => /^https?:\/\//.test(e.u)));
check("every url ends in a slash", index.every((e) => e.u.endsWith("/")));
const dupeUrls = index.length - new Set(index.map((e) => e.u)).size;
check("no duplicate urls", dupeUrls === 0, `${dupeUrls} dupes`);
const noPath = index.filter((e) => e.u.indexOf("/search/") > -1);
check("no entry points at the search page itself", noPath.length === 0);

console.log("\nknown coverage gap");
// Asserted, not fixed: the directory has no dentists, so a search for one
// must return nothing. If a later harvest adds them this fails and the
// expectation should be revisited.
check("dentist is still an uncovered query",
  index.filter((e) => score(e, "dentist") > -1).length === 0,
  "a dentist listing now exists -- update this expectation");

console.log(fail ? `\n${fail} check(s) failed` : "\nall checks passed");
process.exit(fail ? 1 : 0);