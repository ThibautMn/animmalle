// Les mots d'une recherche sont séparés par un ou plusieurs espaces et tous doivent être trouvés (ET).
export function splitTerms(values) {
  const list = Array.isArray(values) ? values : [values];
  const seen = new Set();
  const terms = [];
  for (const value of list) {
    for (const word of String(value ?? "").split(/\s+/)) {
      const key = word.toLocaleLowerCase("fr");
      if (word && !seen.has(key)) {
        seen.add(key);
        terms.push(word);
      }
    }
  }
  return terms;
}

// Découpe un texte en segments ; ceux qui contiennent un terme recherché ont hit = true.
export function highlightParts(text, terms) {
  const value = text || "";
  const sorted = [...terms].filter(Boolean).sort((a, b) => b.length - a.length);
  if (!value || !sorted.length)
    return value ? [{ text: value, hit: false }] : [];
  const pattern = sorted
    .map((term) => term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
    .join("|");
  return value
    .split(new RegExp(`(${pattern})`, "i"))
    .map((part, index) => ({ text: part, hit: index % 2 === 1 }))
    .filter((part) => part.text);
}

// Numéros de pages affichés : première, dernière, page courante et ses voisines (null = coupure).
export function pageEntries(page, last) {
  const wanted = new Set([1, last]);
  for (let n = page - 1; n <= page + 1; n++)
    if (n >= 1 && n <= last) wanted.add(n);
  const entries = [];
  let previous = 0;
  for (const n of [...wanted].sort((a, b) => a - b)) {
    if (n - previous === 2) entries.push(previous + 1);
    else if (n - previous > 2) entries.push(null);
    entries.push(n);
    previous = n;
  }
  return entries;
}
