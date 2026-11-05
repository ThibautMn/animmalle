export const animationFields = [
  ['description', 'Description'],
  ['objectifs', 'Objectifs'],
  ['pre_anim', 'Avant l’animation'],
  ['post_anim', 'Après l’animation'],
  ['public_specifique', 'Public spécifique']
]
export const sequenceFields = [
  ['description', 'Déroulement'],
  ['objectifs', 'Objectifs'],
  ['materiel_div', 'Matériel complémentaire']
]
export const materialFields = [
  ['description', 'Description / Consigne'],
  ['variante', 'Variante'],
  ['materiel', 'Matériel']
]
export const sequenceRefs = [
  ['fk_type_seq_id', 'ref.type_seq', 'Partie'],
  ['fk_approche_id', 'ref.approches', 'Approche'],
  ['fk_modalite_id', 'ref.modalites', 'Modalité'],
  ['fk_duree_id', 'ref.duree_seq', 'Durée']
]
export function newSequence() {
  return {
    titre: '',
    description: '',
    objectifs: '',
    materiel_div: '',
    fk_type_seq_id: null,
    fk_approche_id: null,
    fk_modalite_id: null,
    fk_duree_id: null,
    materiel: []
  }
}
export function animationPayload(item) {
  const keys = [
    'titre',
    'statut',
    'description',
    'objectifs',
    'pre_anim',
    'post_anim',
    'public_specifique',
    'lieu',
    'fk_duree_id',
    'tags'
  ]
  return {
    ...Object.fromEntries(keys.map((key) => [key, item[key]])),
    sequences: item.sequences.map((seq) =>
      Object.fromEntries(
        ['id', ...Object.keys(newSequence())]
          .filter((key) => seq[key] !== undefined)
          .map((key) => [key, seq[key]])
      )
    )
  }
}
export function materialPayload(item) {
  return Object.fromEntries(
    [
      'nom',
      'fk_type_mat_id',
      'description',
      'localisation',
      'variante',
      'difficulte_id',
      'materiel',
      'fk_type_mat_outil_id',
      'thematiques'
    ].map((key) => [key, item[key]])
  )
}
export function moveSequence(items, index, delta) {
  const target = index + delta
  if (target < 0 || target >= items.length) return
  const [item] = items.splice(index, 1)
  items.splice(target, 0, item)
}

export function downloadFilename(disposition) {
  const encoded = /filename\*=UTF-8''([^;]+)/i.exec(disposition || '')
  const plain = /filename="([^"]+)"|filename=([^;]+)/i.exec(disposition || '')
  let name = plain?.[1] || plain?.[2] || 'ressource'
  if (encoded) {
    try {
      name = decodeURIComponent(encoded[1])
    } catch {
      /* Nom simple de secours */
    }
  }
  return name.replace(/[\\/\x00-\x1f]/g, '_').trim() || 'ressource'
}
