import assert from "node:assert/strict";
import test from "node:test";
import { highlightParts, pageEntries, splitTerms } from "../lib/search.mjs";

test("les mots sont séparés par un ou plusieurs espaces, sans doublon", () => {
  assert.deepEqual(splitTerms("  jeux   castor "), ["jeux", "castor"]);
  assert.deepEqual(splitTerms(["jeux castor", "Castor loutre"]), [
    "jeux",
    "castor",
    "loutre",
  ]);
  assert.deepEqual(splitTerms(" \t "), []);
  assert.deepEqual(splitTerms(undefined), []);
});

test("chaque mot trouvé est surligné, sans tenir compte de la casse", () => {
  const parts = highlightParts("Le Castor joue aux jeux", ["jeux", "castor"]);
  assert.deepEqual(
    parts.filter((part) => part.hit).map((part) => part.text),
    ["Castor", "jeux"],
  );
  assert.equal(
    parts.map((part) => part.text).join(""),
    "Le Castor joue aux jeux",
  );
});

test("les caractères spéciaux sont recherchés littéralement", () => {
  assert.deepEqual(highlightParts("a (b) c", ["(b)"]), [
    { text: "a ", hit: false },
    { text: "(b)", hit: true },
    { text: " c", hit: false },
  ]);
  assert.deepEqual(highlightParts("", ["x"]), []);
  assert.deepEqual(highlightParts("texte", []), [
    { text: "texte", hit: false },
  ]);
});

test("la pagination garde les extrémités et la page courante", () => {
  assert.deepEqual(pageEntries(1, 1), [1]);
  assert.deepEqual(pageEntries(1, 3), [1, 2, 3]);
  assert.deepEqual(pageEntries(5, 10), [1, null, 4, 5, 6, null, 10]);
  assert.deepEqual(pageEntries(3, 10), [1, 2, 3, 4, null, 10]);
});
