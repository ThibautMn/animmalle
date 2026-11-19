<script setup>
import { formatMinutes, sequenceRefs } from '../../lib/forms.mjs'
import { toPlainText } from '../../lib/richtext.mjs'
// Fenêtre modale listant toutes les séquences existantes pour en ajouter une copie à l'animation en cours.
const emit = defineEmits(['add'])
const api = useApi()
const catalog = useCatalog()
const dialog = ref(null)
const opened = ref(false)
const text = ref('')
// Un filtre par famille de référence (partie, approche, modalité) : identifiants cochés.
const filters = ref(Object.fromEntries(sequenceRefs.map(([key]) => [key, []])))
const queryKeys = {
  fk_type_seq_id: 'type',
  fk_approche_id: 'approche',
  fk_modalite_id: 'modalite'
}
const items = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const busy = ref(false)
const error = ref('')
let requestId = 0
let timer = null
const pageCount = computed(() => Math.max(1, Math.ceil(total.value / pageSize)))
async function search() {
  const current = ++requestId
  busy.value = true
  error.value = ''
  try {
    // Chaque mot est un critère distinct : tous doivent être présents (ET).
    const terms = text.value.split(/\s+/).filter(Boolean)
    const query = { page: page.value, page_size: pageSize }
    if (terms.length) query.q = terms
    for (const [key, name] of Object.entries(queryKeys))
      if (filters.value[key].length) query[name] = filters.value[key]
    const result = await api('/sequences', { query })
    if (current !== requestId) return
    items.value = result.items
    total.value = result.total
  } catch (e) {
    if (current === requestId) error.value = e.message
  } finally {
    if (current === requestId) busy.value = false
  }
}
watch([text, filters], () => {
  page.value = 1
  clearTimeout(timer)
  timer = setTimeout(search, 300)
}, { deep: true })
function go(target) {
  if (target < 1 || target > pageCount.value) return
  page.value = target
  search()
}
function excerpt(seq) {
  const plain = toPlainText(seq.objectifs || seq.description)
  return plain.length > 200 ? `${plain.slice(0, 200)}…` : plain
}
async function open() {
  opened.value = true
  dialog.value.showModal()
  try {
    await catalog.load()
  } catch {
    // Les libellés resteront vides ; la liste reste utilisable.
  }
  await search()
}
function close() {
  dialog.value?.close()
}
onBeforeUnmount(() => clearTimeout(timer))
defineExpose({ open, close })
</script>
<template>
  <dialog
    ref="dialog"
    class="media-add-dialog sequence-picker-dialog"
    aria-label="Ajouter une séquence existante"
    @close="opened = false"
    @click="$event.target === dialog && close()"
  >
    <div class="toolbar">
      <h2>Ajouter une séquence existante</h2>
      <PButton
        type="button"
        class="icon-button secondary dialog-close"
        aria-label="Fermer"
        title="Fermer"
        @click="close"
        ><ActionIcon name="close"
      /></PButton>
    </div>
    <div v-if="opened" class="sequence-picker">
      <div class="picker-filters">
        <label
          >Recherche<input
            v-model="text"
            type="search"
            maxlength="100"
            placeholder="Titre, objectifs, déroulement, animation…"
        /></label>
        <fieldset v-for="[key, family, label] in sequenceRefs" :key="key">
          <legend>{{ label }}</legend>
          <div class="picker-checks">
            <label
              v-for="term in catalog.family(family)"
              :key="term.id"
              class="check"
              ><input v-model="filters[key]" type="checkbox" :value="term.id" />{{
                term.label
              }}</label
            >
          </div>
        </fieldset>
      </div>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <p aria-live="polite">
        {{ total }} séquence{{ total > 1 ? 's' : '' }}
      </p>
      <ul class="picker-results" :aria-busy="busy">
        <li v-for="seq in items" :key="seq.id" class="card">
          <div>
            <h3>{{ seq.titre }}</h3>
            <ul class="chips" aria-label="Caractéristiques">
              <li v-for="[key, , label] in sequenceRefs" :key="key" :title="label">
                {{ catalog.label(seq[key]) }}
              </li>
              <li v-if="formatMinutes(seq.duree_minutes)">
                {{ formatMinutes(seq.duree_minutes) }}
              </li>
            </ul>
            <p>{{ excerpt(seq) }}</p>
            <small>Animation : {{ seq.animation.titre }}</small>
          </div>
          <PButton
            type="button"
            label="Ajouter"
            data-tooltip="Ajoute une copie de cette séquence à l'animation"
            @click="emit('add', seq)"
          />
        </li>
      </ul>
      <p v-if="!busy && !items.length && !error">Aucune séquence trouvée.</p>
      <nav v-if="pageCount > 1" class="pagination" aria-label="Pagination">
        <PButton
          class="secondary"
          label="Précédente"
          :disabled="page === 1 || busy"
          @click="go(page - 1)"
        />
        <span>Page {{ page }} / {{ pageCount }}</span>
        <PButton
          class="secondary"
          label="Suivante"
          :disabled="page === pageCount || busy"
          @click="go(page + 1)"
        />
      </nav>
    </div>
  </dialog>
</template>
<style>
.sequence-picker-dialog {
  width: min(1000px, 96vw);
  height: 90vh;
  overflow-y: auto;
}
.sequence-picker-dialog .picker-filters {
  border: 1.5px solid #d6cfee;
  background: #f5f3fb;
  box-shadow: 0 2px 8px rgb(74 63 122 / 12%);
  border-radius: var(--radius);
  padding: 12px 16px;
  display: grid;
  gap: 10px;
}
.sequence-picker-dialog .picker-filters fieldset {
  border: 0;
  padding: 0;
  margin: 0;
}
.sequence-picker-dialog .picker-filters legend {
  padding: 0;
  margin-bottom: 0;
  line-height: 1.2;
}
.sequence-picker-dialog .picker-checks {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 18px;
}
.sequence-picker-dialog .picker-checks .check {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 400;
}
.sequence-picker-dialog .picker-checks .check input {
  margin: 0;
  width: auto;
}
.sequence-picker-dialog .picker-results {
  list-style: none;
  padding: 0;
  display: grid;
  gap: 0.75rem;
}
.sequence-picker-dialog .picker-results .chips {
  display: flex;
  flex-flow: row wrap;
  align-items: center;
  gap: 6px;
  list-style: none;
  padding: 0;
  margin: 4px 0;
}
.sequence-picker-dialog .picker-results .chips > li {
  display: inline-flex;
  margin: 0;
  padding: 2px 10px;
  border-radius: 999px;
  background: var(--c-primary-soft);
  border: 1px solid var(--c-primary-mid);
  color: var(--c-text);
  font-size: 0.85rem;
}
.sequence-picker-dialog .picker-results > li {
  background: var(--c-surface);
  border: 1.5px solid #cfc3b0;
  box-shadow: 0 2px 8px rgb(60 40 10 / 14%);
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 1rem;
}
</style>
