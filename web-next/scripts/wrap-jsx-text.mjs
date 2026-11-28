// Wrap visible English JSX text in <T> for translation (lib/ui-i18n.ts).
//
//   node scripts/wrap-jsx-text.mjs <file.tsx> [...more]
//
// Uses the TypeScript parser, so only real JsxText nodes are touched, never
// code that happens to sit between a ">" and a "<". Text with no letters,
// text already inside <T>, and text inside <code>/<pre>/<script>/<style>
// is left alone. Surrounding whitespace is kept outside the <T>.
import fs from "node:fs";
import ts from "typescript";

const SKIP_PARENTS = new Set(["T", "code", "pre", "script", "style", "title", "option"]);
const LITERALS = process.argv.includes("--literals");

function tagName(node) {
  const opening = node.openingElement ?? node;
  const name = opening.tagName;
  return name ? name.getText() : "";
}

for (const file of process.argv.slice(2).filter((a) => !a.startsWith("--"))) {
  const src = fs.readFileSync(file, "utf8");
  const sf = ts.createSourceFile(file, src, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const edits = [];
  const visit = (node) => {
    if (node.kind === ts.SyntaxKind.JsxText) {
      const raw = node.getText(sf);
      const text = raw.replace(/\s+/g, " ").trim();
      const parent = node.parent;
      const parentTag = parent && ts.isJsxElement(parent) ? tagName(parent) : "";
      if (/[A-Za-z]{2,}/.test(text) && !SKIP_PARENTS.has(parentTag) && !text.includes("{") && !text.includes("}")) {
        const start = node.getStart(sf);
        const lead = raw.match(/^\s*/)[0];
        const trail = raw.match(/\s*$/)[0];
        // Keep a single space at either edge when the original had one on the
        // same line, so "Best {name} player" keeps its spacing.
        const leadOut = lead.includes("\n") ? lead : lead ? " " : "";
        const trailOut = trail.includes("\n") ? trail : trail ? " " : "";
        const escaped = text.replace(/\\/g, "\\\\").replace(/"/g, '\\"');
        edits.push({ start, end: start + raw.length, text: `${leadOut}<T>{"${escaped}"}</T>${trailOut}` });
      }
    }
    // String literals rendered as JSX children, directly or as a branch of a
    // ternary / && / ?? inside a child expression: {x ? "Rising" : "Stable"}.
    // Attributes are excluded (their JsxExpression's parent is a JsxAttribute).
    if ((ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) && LITERALS) {
      let p = node.parent;
      let ok = false;
      while (p) {
        if (ts.isConditionalExpression(p) || ts.isParenthesizedExpression(p)
            || (ts.isBinaryExpression(p) && [ts.SyntaxKind.AmpersandAmpersandToken, ts.SyntaxKind.BarBarToken, ts.SyntaxKind.QuestionQuestionToken].includes(p.operatorToken.kind) && p.right === node)) {
          if (ts.isConditionalExpression(p) && p.condition === node) break;
          p = p.parent;
          continue;
        }
        if (ts.isJsxExpression(p) && p.parent && (ts.isJsxElement(p.parent) || ts.isJsxFragment(p.parent))) {
          // The element that renders this expression; never wrap inside <T>.
          ok = !(ts.isJsxElement(p.parent) && SKIP_PARENTS.has(tagName(p.parent)));
        }
        break;
      }
      const text = node.text;
      if (ok && /[A-Za-z]{2,}/.test(text) && !/^[\w-]+\.(png|jpe?g|webp|svg)$/.test(text) && !text.startsWith("/")) {
        {
          const escaped = text.trim().replace(/\\/g, "\\\\").replace(/"/g, '\\"');
          const lead = text.match(/^\s*/)[0] ? " " : "";
          const trail = text.match(/\s*$/)[0] ? " " : "";
          edits.push({ start: node.getStart(sf), end: node.getEnd(), text: `<>${lead}<T>{"${escaped}"}</T>${trail}</>` });
        }
      }
    }
    ts.forEachChild(node, visit);
  };
  visit(sf);
  if (!edits.length) { console.log(`${file}: 0`); continue; }
  let out = src;
  for (const e of edits.sort((a, b) => b.start - a.start)) out = out.slice(0, e.start) + e.text + out.slice(e.end);
  if (!/from "@\/components\/t"/.test(out)) {
    const directive = out.match(/^\s*["']use client["'];?\s*\n/);
    const firstImport = out.indexOf("\nimport ");
    const insertAt = directive ? directive[0].length : out.startsWith("import ") ? 0 : firstImport + 1;
    out = out.slice(0, insertAt) + 'import { T } from "@/components/t";\n' + out.slice(insertAt);
  }
  fs.writeFileSync(file, out);
  console.log(`${file}: ${edits.length}`);
}
