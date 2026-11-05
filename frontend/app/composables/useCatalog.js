export function useCatalog() {
  const items = useState('thesaurus', () => [])
  const api = useApi()
  const load = async () => {
    items.value = (await api('/thesaurus')).items
  }
  const family = (name) => items.value.filter((item) => item.reference === name)
  const label = (id) => items.value.find((item) => item.id === id)?.label || ''
  return { items, load, family, label }
}
