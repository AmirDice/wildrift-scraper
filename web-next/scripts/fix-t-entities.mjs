// After wrap-jsx-text: unwrap <T> around pure HTML entities (&rarr;) and
// decode entities inside wrapped strings (&rsquo;s -> ’s), because a string
// literal renders "&rsquo;" literally where JSX text decoded it.
import fs from "node:fs";

const ENT = { rsquo: "’", lsquo: "‘", ldquo: "“", rdquo: "”", rarr: "→", larr: "←", minus: "−", middot: "·", amp: "&", mdash: "—", ndash: "–", hellip: "…", nbsp: " ", apos: "'", quot: '\\"', times: "×" };
const decode = (s) => s.replace(/&([a-z]+);/g, (m, name) => (name in ENT ? ENT[name] : m));

for (const file of process.argv.slice(2)) {
  const src = fs.readFileSync(file, "utf8");
  let n = 0;
  const out = src.replace(/<T>\{"((?:[^"\\]|\\.)*)"\}<\/T>/g, (whole, inner) => {
    if (!inner.includes("&")) return whole;
    n++;
    const decoded = decode(inner);
    // Nothing translatable left (an arrow, a minus): put the plain text back.
    if (!/[A-Za-z]{2,}/.test(decoded.replace(/\\"/g, ""))) return inner;
    return `<T>{"${decoded}"}</T>`;
  });
  if (n) { fs.writeFileSync(file, out); console.log(`${file}: ${n}`); }
}
