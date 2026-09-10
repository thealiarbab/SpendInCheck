/**
 * Regenerate server/currency.py from the runtime's own currency data.
 *
 *     node scripts/currencies.js > /tmp/currencies.txt
 *
 * There is no need to find a list of the world's currencies and paste it in:
 * every JavaScript runtime ships one, kept current with CLDR.
 * `Intl.supportedValuesOf("currency")` is every code ISO 4217 lists, and
 * `resolvedOptions().maximumFractionDigits` is how many places each is
 * divided into. Reading both from the same place the browser formats with
 * is what stops the server's idea of a currency drifting from the client's.
 *
 * Prints the three sets the Python module needs, already wrapped to width.
 */

const all = Intl.supportedValuesOf("currency");

const digitsOf = (code) =>
  new Intl.NumberFormat("en", { style: "currency", currency: code })
    .resolvedOptions().maximumFractionDigits;

const zero = all.filter((code) => digitsOf(code) === 0);
const three = all.filter((code) => digitsOf(code) === 3);

/** Wrap a list of codes into indented Python-source lines. */
function wrap(list) {
  const lines = [];
  let line = "    ";
  for (const code of list) {
    if (line.length + code.length + 4 > 78) {
      lines.push(line.trimEnd());
      line = "    ";
    }
    line += `"${code}", `;
  }
  if (line.trim()) lines.push(line.trimEnd());
  return lines.join("\n");
}

console.log(`# ${all.length} currencies, ${zero.length} with no minor unit, ` +
            `${three.length} divided into thousandths.`);
console.log("\nZERO_DECIMAL = frozenset({");
console.log(wrap(zero));
console.log("})\n\nTHREE_DECIMAL = frozenset({");
console.log(wrap(three));
console.log("})\n\nALL = (");
console.log(wrap(all));
console.log(")");
