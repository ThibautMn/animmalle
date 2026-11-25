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

// Caractère sans accent ni majuscule, toujours d'un seul caractère (même règle que fold côté backend).
function foldChar(char) {
  const base = char.normalize("NFD")[0].toLowerCase();
  return base.length === 1 ? base : char;
}

// Texte replié de même longueur que l'original : les positions trouvées s'appliquent au texte affiché.
export function fold(text) {
  let folded = "";
  for (let index = 0; index < text.length; index++)
    folded += foldChar(text[index]);
  return folded;
}

// Découpe un texte en segments ; ceux qui contiennent un terme recherché (sans tenir compte
// de la casse ni des accents) ont hit = true.
export function highlightParts(text, terms) {
  const value = text || "";
  const sorted = [...new Set(terms.filter(Boolean).map(fold))].sort(
    (a, b) => b.length - a.length,
  );
  if (!value || !sorted.length)
    return value ? [{ text: value, hit: false }] : [];
  const pattern = new RegExp(
    sorted
      .map((term) => term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
      .join("|"),
    "g",
  );
  const folded = fold(value);
  const parts = [];
  let last = 0;
  for (const match of folded.matchAll(pattern)) {
    if (match.index > last)
      parts.push({ text: value.slice(last, match.index), hit: false });
    last = match.index + match[0].length;
    parts.push({ text: value.slice(match.index, last), hit: true });
  }
  if (last < value.length) parts.push({ text: value.slice(last), hit: false });
  return parts;
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
