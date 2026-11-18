<script setup>
// Mode « outil » : une seule pièce jointe locale, sans nom ni thématiques ; le fichier
// et son type sont renvoyés à la fiche, qui les enregistre avec l'outil.
const props = defineProps({
  tool: Boolean,
  typeId: { type: Number, default: null }
})
const emit = defineEmits(['add', 'pick-file'])
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
  if (!allowed.value) loadAllowed()
  if (props.tool) typeId.value = props.typeId
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
// Extensions acceptées par le serveur ; null tant qu'elles ne sont pas connues (aucun blocage alors).
const allowed = ref(null)
async function loadAllowed() {
  try {
    allowed.value = (await api('/files/config')).allowed_extensions.map((item) => item.toLowerCase())
  } catch {
    allowed.value = null
  }
}
const extension = computed(() => (file.value ? file.value.name.split('.').pop().toLowerCase() : ''))
const forbidden = computed(
  () => Boolean(file.value) && Boolean(allowed.value) && !allowed.value.includes(extension.value)
)
const fileSize = computed(() => {
  const bytes = file.value?.size
  if (bytes == null) return ''
  if (bytes < 1024) return `${bytes} o`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1).replace('.', ',')} Ko`
  return `${(bytes / 1024 / 1024).toFixed(1).replace('.', ',')} Mo`
})
const IMAGES = ['jpg', 'jpeg', 'png', 'gif', 'webp']
const AUDIOS = ['mp3', 'wma', 'wav', 'ogg', 'm4a', 'aac', 'flac']
const VIDEOS = ['mp4', 'm4v', 'mov', 'avi', 'wmv', 'mpg', 'mpeg', 'mkv', 'webm', 'flv', '3gp']
const normalize = (text) => text.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase()
// Type de pièce jointe proposé d'après le format : photo, bande-son, vidéo, sinon support.
function guessType(filename) {
  const extension = filename.split('.').pop().toLowerCase()
  const wanted = IMAGES.includes(extension)
    ? 'photo'
    : AUDIOS.includes(extension)
      ? 'bande-son'
      : VIDEOS.includes(extension)
        ? 'video'
        : 'support'
  return catalog.family('ref.type_mat').find((type) => normalize(type.label) === wanted)?.id ?? null
}
// Aperçu local du fichier choisi, avant tout envoi.
const previewUrl = ref('')
const previewKind = computed(() => {
  if (!file.value) return ''
  const extension = file.value.name.split('.').pop().toLowerCase()
  if (IMAGES.includes(extension)) return 'image'
  if (AUDIOS.includes(extension)) return 'audio'
  if (VIDEOS.includes(extension)) return 'video'
  if (extension === 'pdf') return 'pdf'
  return 'file'
})
watch(file, (value) => {
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
  previewUrl.value = value ? URL.createObjectURL(value) : ''
})
onBeforeUnmount(() => previewUrl.value && URL.revokeObjectURL(previewUrl.value))
function onFile(event) {
  file.value = event.target.files[0] || null
  if (props.tool && file.value) typeId.value = guessType(file.value.name) ?? typeId.value
  if (file.value && !name.value) name.value = file.value.name.replace(/\.[^.]+$/, '').slice(0, 100)
}
async function upload() {
  if (!file.value || !typeId.value || forbidden.value) return
  if (props.tool) {
    emit('pick-file', { file: file.value, typeId: Number(typeId.value) })
    close()
    return
  }
  busy.value = true
  error.value = ''
  try {
    const body = new FormData()
    body.append('data', JSON.stringify({ nom: name.value, fk_type_mat_id: Number(typeId.value), thematiques: themes.value }))
    body.append('file', file.value)
    const media = await api('/media', { method: 'POST', body })
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
    const result = await api('/media', {
      query: { q: query.value, type: types.value, page: page.value, page_size: PAGE_SIZE }
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
    :class="['media-add-dialog', { 'media-library': !tool && tab !== 'upload' }]"
    aria-label="Ajouter un média"
    @close="reset"
    @click="$event.target === dialog && close()"
  >
    <div class="toolbar">
      <h2>Ajouter un média</h2>
      <PButton
        type="button"
        class="icon-button secondary dialog-close"
        aria-label="Fermer"
        title="Fermer"
        @click="close"
        ><ActionIcon name="close"
      /></PButton>
    </div>
    <div v-if="!tool" class="media-add-tabs" role="tablist">
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
      <div v-if="file" class="file-details">
        <div class="file-preview" aria-label="Aperçu du fichier">
          <img v-if="previewKind === 'image'" :src="previewUrl" :alt="file.name" />
          <video v-else-if="previewKind === 'video'" :src="previewUrl" controls preload="metadata" />
          <audio v-else-if="previewKind === 'audio'" :src="previewUrl" controls />
          <iframe v-else-if="previewKind === 'pdf'" :src="previewUrl" :title="file.name" />
          <p v-else class="file-preview-name">{{ extension.toUpperCase() }}</p>
        </div>
        <div class="file-info">
          <p class="file-info-name">{{ file.name }}</p>
          <p v-if="fileSize" class="muted">{{ fileSize }}</p>
          <p v-if="forbidden" role="alert" class="file-forbidden">Format de fichier non autorisé</p>
          <label>
            {{ tool ? 'Type de pièce jointe' : 'Type de média' }}
            <select v-model="typeId" required>
              <option :value="null" disabled>Choisir…</option>
              <option v-for="type in catalog.family('ref.type_mat')" :key="type.id" :value="type.id">
                {{ type.label }}
              </option>
            </select>
          </label>
        </div>
      </div>
      <label v-if="!tool">Nom du média<input v-model="name" required maxlength="100" /></label>
      <TagPicker
        v-if="!tool"
        v-model="themes"
        :items="catalog.family('ref.thematiques')"
        legend="Thématiques"
      />
      <PButton type="submit" :label="tool ? 'Ajouter' : 'Télécharger et ajouter'" :disabled="busy || forbidden" />
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
