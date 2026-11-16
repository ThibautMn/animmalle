<script setup>
const emit = defineEmits(['add'])
const api = useApi()
const catalog = useCatalog()
const dialog = ref(null)
const tab = ref('upload')
const error = ref('')
const busy = ref(false)
// Téléchargement depuis l'ordinateur
const file = ref(null)
const name = ref('')
const typeId = ref(null)
const themes = ref([])
// Médiathèque
const query = ref('')
const types = ref([])
const results = ref([])
const searched = ref(false)
const page = ref(1)
const total = ref(0)
const PAGE_SIZE = 12  // 3 lignes de 4 vignettes
let timer = null
const tabs = [
  ['upload', "Depuis l'ordinateur"],
  ['pnc', 'Médiathèque du PNC'],
  ['library', 'Médiathèque Anim’Malle']
]
function open() {
  error.value = ''
  tab.value = 'upload'
  dialog.value.showModal()
}
function close() {
  dialog.value?.close()
}
function reset() {
  file.value = null
  name.value = ''
  typeId.value = null
  themes.value = []
  query.value = ''
  types.value = []
  results.value = []
  searched.value = false
  page.value = 1
  total.value = 0
  error.value = ''
}
defineExpose({ open })
function onFile(event) {
  file.value = event.target.files[0] || null
  if (file.value && !name.value) name.value = file.value.name.replace(/\.[^.]+$/, '').slice(0, 100)
}
async function upload() {
  if (!file.value || !typeId.value) return
  busy.value = true
  error.value = ''
  try {
    const body = new FormData()
    body.append('data', JSON.stringify({ nom: name.value, fk_type_mat_id: Number(typeId.value), thematiques: themes.value }))
    body.append('file', file.value)
    const media = await api('/materials', { method: 'POST', body })
    emit('add', media)
    close()
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}
async function search(reset = true) {
  if (reset) page.value = 1
  busy.value = true
  error.value = ''
  try {
    const result = await api('/materials', {
      query: { kind: 'media', q: query.value, type: types.value, page: page.value, page_size: PAGE_SIZE }
    })
    results.value = result.items
    total.value = result.total
    searched.value = true
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}
const pager = computed(() => ({
  page: page.value,
  pageCount: Math.ceil(total.value / PAGE_SIZE),
  busy: busy.value
}))
function goTo(value) {
  page.value = value
  search(false)
}
function searchSoon() {
  clearTimeout(timer)
  timer = setTimeout(() => search(), 300)
}
function pick(media) {
  emit('add', media)
  close()
}
watch(types, () => dialog.value?.open && search())
watch(tab, (value) => {
  error.value = ''
  if (value === 'library' && !searched.value) search()
})
onBeforeUnmount(() => clearTimeout(timer))
</script>
<template>
  <dialog
    ref="dialog"
    :class="['media-add-dialog', { 'media-library': tab !== 'upload' }]"
    aria-label="Ajouter un média"
    @close="reset"
    @click="$event.target === dialog && close()"
  >
    <div class="toolbar">
      <h2>Ajouter un média</h2>
      <PButton type="button" label="Fermer" @click="close" />
    </div>
    <div class="media-add-tabs" role="tablist">
      <button
        v-for="[key, label] in tabs"
        :id="`media-tab-${key}`"
        :key="key"
        type="button"
        role="tab"
        :aria-selected="tab === key"
        :class="{ active: tab === key }"
        @click="tab = key"
      >
        {{ label }}
      </button>
    </div>
    <p v-if="error" role="alert" class="error">{{ error }}</p>
    <form
      v-if="tab === 'upload'"
      role="tabpanel"
      aria-labelledby="media-tab-upload"
      @submit.prevent="upload"
    >
      <label class="file-picker">
        Fichier
        <input type="file" required class="file-picker-input" @change="onFile" />
        <span class="file-picker-row">
          <span class="file-picker-button">Parcourir…</span>
          <span class="file-picker-name">{{ file ? file.name : 'Aucun fichier sélectionné' }}</span>
        </span>
      </label>
      <label>Nom du média<input v-model="name" required maxlength="100" /></label>
      <label>
        Type de média
        <select v-model="typeId" required>
          <option :value="null" disabled>Choisir…</option>
          <option v-for="type in catalog.family('ref.type_mat')" :key="type.id" :value="type.id">
            {{ type.label }}
          </option>
        </select>
      </label>
      <TagPicker
        v-model="themes"
        :items="catalog.family('ref.thematiques')"
        legend="Thématiques"
      />
      <PButton type="submit" label="Télécharger et ajouter" :disabled="busy" />
    </form>
    <div v-else-if="tab === 'library'" role="tabpanel" aria-labelledby="media-tab-library">
      <p class="pnc-intro">Ces médias sont ceux déjà enregistrés dans les autres animations</p>
      <input
        v-model="query"
        type="search"
        placeholder="Rechercher un média…"
        aria-label="Rechercher dans la médiathèque"
        @input="searchSoon"
        @keydown.enter.prevent="search()"
      />
      <TagPicker
        v-model="types"
        :items="catalog.family('ref.type_mat')"
        legend="Types de média"
        plain
      />
      <MediaPager v-bind="pager" @go="goTo" />
      <p v-if="busy" role="status">Recherche…</p>
      <p v-else-if="searched && !results.length">Aucun média trouvé.</p>
      <SequenceMedia
        v-if="results.length"
        :key="`${query}-${page}`"
        :items="results"
        selectable
        @select="pick"
      />
      <MediaPager v-bind="pager" @go="goTo" />
    </div>
    <div v-else role="tabpanel" aria-labelledby="media-tab-pnc">
      <PncLibrary @add="pick" />
    </div>
  </dialog>
</template>
