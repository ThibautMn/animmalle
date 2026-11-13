export function useCatalog() {
  const items = useState('thesaurus', () => [])
  const api = useApi()
  const load = async () => {
    items.value = (await api('/thesaurus')).items
  }
  const family = (name) => items.value.filter((item) => item.reference === name)
  const label = (id) => items.value.find((item) => item.id === id)?.label || ''
  const sequenceKind = (seq) => {
    const name = label(seq.fk_type_seq_id)
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .toLowerCase()
    if (name.startsWith('intro')) return 'seq-intro'
    if (name.startsWith('developpement')) return 'seq-dvp'
    if (name.startsWith('conclu')) return 'seq-conclu'
    return ''
  }
  return { items, load, family, label, sequenceKind }
}
