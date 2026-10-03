// Drive sandton.js's search module against a real DOM so the render path is
// exercised, not just the scoring helpers.
//
//     node scripts/test_search_render.js
//
// Uses jsdom if it is installed; otherwise skips rather than reporting a
// false pass. Top-level await, so run with a Node that supports it (18+).
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..");
const IDX = path.join(ROOT, "site", "assets", "search-index.json");
const JS = path.join(ROOT, "scripts", "assets", "sandton.js");

let JSDOM;
try {
  ({ JSDOM } = require("jsdom"));
} catch {
  console.log("skip: jsdom not installed (npm i -D jsdom) -- " +
              "render path not exercised");
  process.exit(0);
}

const index = JSON.parse(fs.readFileSync(IDX, "utf8"));
const js = fs.readFileSync(JS, "utf8");

// A stand-in XHR that answers from the real index synchronously.
function makeDom() {
  const dom = new JSDOM(
    `<!doctype html><html><body>
       <input id="si-nav-toggle" aria-expanded="false">
       <nav id="si-nav" class="site"></nav>
       <form id="si-search-form" data-index="index.json"
             data-base="https://example.test/">
         <input id="si-search-input" name="q" type="search">
         <button type="submit">Search</button>
       </form>
       <p id="si-search-status"></p>
       <div id="si-search-hints"></div>
       <div class="results" id="si-search-results"></div>
     </body></html>`,
    { url: "https://example.test/search/", runScripts: "outside-only" }
  );

  const win = dom.window;
  win.XMLHttpRequest = class {
    open() {}
    send() {
      this.status = 200;
      this.responseText = JSON.stringify(index);
      this.readyState = 4;
      this.onreadystatechange();
    }
  };

  /* sandton.js defers boot() to DOMContentLoaded while readyState is
     "loading". Evaluating before the document finishes therefore registers a
     listener for an event that has already fired and nothing ever boots --
     so wait for load, then evaluate. */
  return new Promise((resolve) => {
    if (win.document.readyState === "complete") {
      win.eval(js);
      resolve(dom);
      return;
    }
    win.addEventListener("load", () => {
      win.eval(js);
      resolve(dom);
    });
  });
}

async function main() {

let fail = 0;
function check(label, cond, detail) {
  if (cond) { console.log("  ok    " + label); }
  else { console.log("  FAIL  " + label + (detail ? " -- " + detail : "")); fail += 1; }
}

function search(dom, q) {
  const win = dom.window;
  const doc = win.document;
  const input = doc.getElementById("si-search-input");
  const results = doc.getElementById("si-search-results");
  const status = doc.getElementById("si-search-status");
  const form = doc.getElementById("si-search-form");

  input.value = q;
  results.innerHTML = "";
  status.textContent = "";
  form.dispatchEvent(new win.Event("submit", { cancelable: true }));
  return {
    cards: results.querySelectorAll(".result").length,
    status: status.textContent,
    first: results.querySelector(".result h3")
      ? results.querySelector(".result h3").textContent.trim() : null,
    marks: results.querySelectorAll("mark").length,
    empty: !!results.querySelector(".search-empty"),
    html: results.innerHTML,
  };
}

const dom = await makeDom();
const doc = dom.window.document;

console.log("mount");
check("nav toggle is bound", !!doc.getElementById("si-nav-toggle"));

console.log("\nempty query");
let r = search(dom, "");
check("renders no results", r.cards === 0);
check("status is blank", r.status === "");

console.log("\nexact name");
r = search(dom, "woolworths");
check("returns results", r.cards > 0, `${r.cards} cards`);
check("first hit is Woolworths", /woolworths/i.test(r.first || ""), r.first);
check("status counts matches", /match/.test(r.status), r.status);
check("highlights the match", r.marks > 0, `${r.marks} marks`);
check("no empty state", !r.empty);

console.log("\ncase insensitive");
r = search(dom, "WOOLWORTHS");
check("uppercase finds the same rows", r.cards > 0);

console.log("\nsuburb query");
r = search(dom, "rivonia");
check("returns results", r.cards > 0, `${r.cards} cards`);
check("caps at 60", r.cards <= 60, `${r.cards}`);
check("status says first N of M when capped", r.cards === 60
  ? /First 60 of/.test(r.status) : /matches$/.test(r.status), r.status);

console.log("\nno match");
r = search(dom, "zzzznotathing");
check("shows the empty state", r.empty);
check("does not say 'try another word'", !/Try a business name/.test(r.html),
  r.html.slice(0, 200));
check("names the gap honestly", /Nothing in the index matches/.test(r.html));
check("status reports no matches", /No matches/.test(r.status), r.status);

console.log("\nuncovered query");
r = search(dom, "dentist");
check("dentist is uncovered", r.empty);
check("names the gap honestly", /Nothing in the index matches/.test(r.html));
check("offers real section links",
  r.html.indexOf('<a href="https://example.test/') > -1, r.html.slice(0, 300));
check("links are absolute, not relative to /search/",
  r.html.indexOf('href="offices') === -1 && r.html.indexOf('"search/') === -1,
  r.html.slice(0, 300));
check("links are not double-escaped",
  r.html.indexOf("&amp;lt;a") === -1 && r.html.indexOf("&amp;amp;") === -1,
  r.html.slice(0, 300));
check("still states no matches", /No matches/.test(r.status), r.status);

console.log("\naccent handling regression");
// "Décor" splits on the non-ASCII é into fragments, and the resulting
// one-letter "d" used to prefix-match "dentist", offering the furniture
// section to somebody looking for a dentist.
r = search(dom, "dentist");
check("does not offer furniture to a dentist",
  r.html.indexOf("Furniture") === -1, r.html.slice(0, 260));
r = search(dom, "decor");
check("'decor' still reaches Décor despite the accent",
  r.cards > 0 || /D[eé]cor/.test(r.html), r.html.slice(0, 200));

console.log("\nnear miss in the hint");
// Stemming runs when nothing matched, to point at the nearest section.
// "groceries" has no direct hit but stems to "grocer".
r = search(dom, "groceries");
check("no direct match for 'groceries'", r.empty);
check("hint names the nearest section by stem",
  /Supermarkets/.test(r.html), r.html.slice(0, 240));
check("hint links to that section",
  /href="https:\/\/example\.test\/supermarkets\/"/.test(r.html),
  r.html.slice(0, 240));

console.log("\nxss");
r = search(dom, "<img src=x onerror=alert(1)>");
check("markup is not executed", r.html.indexOf("<img") === -1,
  r.html.slice(0, 160));
check("payload appears escaped", r.html.indexOf("&lt;img") > -1);

console.log("\nnav toggle");
const nav = doc.getElementById("si-nav");
const btn = doc.getElementById("si-nav-toggle");
btn.dispatchEvent(new dom.window.Event("click"));
check("opens the menu", nav.className.indexOf("open") > -1, nav.className);
check("sets aria-expanded", btn.getAttribute("aria-expanded") === "true");
btn.dispatchEvent(new dom.window.Event("click"));
check("closes again", nav.className.indexOf("open") === -1);

console.log(fail ? `\n${fail} check(s) failed` : "\nall checks passed");
process.exit(fail ? 1 : 0);

}

main();