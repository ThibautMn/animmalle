import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  downloadFilename,
  animationPayload,
  mediaPayload,
  outilPayload,
  newSequence,
  moveSequence
} from '../lib/forms.mjs'

test('Le remplacement conserve les identifiants, l’ordre et les associations sans renvoyer les champs serveur', () => {
  const first = {
    ...newSequence(),
    id: 42,
    titre: 'Observer',
    materiel: [8, 9]
  }
  const second = { ...newSequence(), titre: 'Comprendre' }
  const item = {
    titre: 'Découverte',
    auteurs: 'Auteur serveur',
    date_modif: '2026-11-05',
    pertinence: {},
    sequences: [first, second],
    tags: [2]
  }
  moveSequence(item.sequences, 1, -1)
  const data = animationPayload(item)
  assert.equal(data.sequences[0].titre, 'Comprendre')
  assert.equal(data.sequences[1].id, 42)
  assert.deepEqual(data.sequences[1].materiel, [8, 9])
  assert.ok(!('id' in data.sequences[0]))
  assert.ok(!('auteurs' in data))
  assert.ok(!('date_modif' in data))
  assert.ok(!('pertinence' in data))
  moveSequence(item.sequences, 0, -1)
  assert.equal(item.sequences[0], second)
})
test('Les fichiers et les identifiants de notice sont exclus du PUT', () => {
  const data = mediaPayload({
    id: 9,
    nom: 'Image',
    has_file: true,
    thematiques: [1, 2]
  })
  assert.equal(data.nom, 'Image')
  assert.deepEqual(data.thematiques, [1, 2])
  assert.ok(!('has_file' in data))
  assert.ok(!('id' in data))
  assert.ok(!('localisation' in data))
})

test('Un outil facilitateur n’envoie que ses propres champs', () => {
  const data = outilPayload({
    id: 3,
    nom: 'Outil',
    fk_type_outil_id: 7,
    difficulte_id: 8,
    variante: 'v',
    materiel: 'm',
    thematiques: [1],
    localisation: 'x'
  })
  assert.deepEqual(Object.keys(data).sort(), [
    'description',
    'difficulte_id',
    'fk_type_mat_outil_id',
    'fk_type_outil_id',
    'materiel',
    'nom',
    'variante'
  ])
})

test('Le nom de téléchargement conserve l’extension et les accents', () => {
  assert.equal(
    downloadFilename('attachment; filename="image.png"'),
    'image.png'
  )
  assert.equal(
    downloadFilename(
      "attachment; filename=fallback.pdf; filename*=UTF-8''C%C3%A9vennes.pdf"
    ),
    'Cévennes.pdf'
  )
  assert.equal(
    downloadFilename('attachment; filename="../test.pdf"'),
    '.._test.pdf'
  )
})
