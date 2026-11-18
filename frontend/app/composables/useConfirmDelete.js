// Fenêtre de confirmation de suppression : retourne une promesse résolue à true (valider) ou false (annuler).
let resolver = null
export function useConfirmDelete() {
  const state = useState('confirm_delete', () => ({ open: false, message: '' }))
  function confirmDelete(message) {
    resolver?.(false)
    state.value = { open: true, message }
    return new Promise((resolve) => {
      resolver = resolve
    })
  }
  function answer(value) {
    state.value = { open: false, message: '' }
    resolver?.(value)
    resolver = null
  }
  return { state, confirmDelete, answer }
}
