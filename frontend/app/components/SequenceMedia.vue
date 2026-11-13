<script setup>
const props = defineProps({ items: { type: Array, required: true } })
const api = useApi()
const catalog = useCatalog()
const sources = ref({})
const errors = ref({})
let disposed = false
const items = computed(() => props.items.filter(Boolean))
const EXTENSIONS = {
  image: ['jpg', 'jpeg', 'png', 'gif', 'webp'],
  video: ['mp4', 'm4v', 'mov', 'avi', 'wmv', 'mpg', 'mpeg', 'mkv', 'webm', 'flv', '3gp'],
  audio: ['mp3', 'wma', 'wav', 'ogg', 'm4a', 'aac', 'flac'],
  pdf: ['pdf'],
  presentation: ['ppt', 'pptx', 'odp'],
  document: ['doc', 'docx', 'odt', 'rtf', 'txt'],
  spreadsheet: ['xls', 'xlsx', 'ods', 'csv'],
  archive: ['zip']
}
// Formats dont le backend fournit une vignette ou un aperçu.
const THUMBNAILED = ['image', 'video', 'pdf', 'presentation', 'document']
const PREVIEWABLE = ['image', 'video', 'audio', 'pdf', 'presentation', 'document', 'spreadsheet']
function kind(item) {
  const extension = (item.extension || '').toLowerCase()
  const found = Object.keys(EXTENSIONS).find((name) => EXTENSIONS[name].includes(extension))
  if (found) return found
  const label = catalog.label(item.fk_type_mat_id).toLocaleLowerCase()
  if (/image|photo/.test(label)) return 'image'
  if (/vid[ée]o|film/.test(label)) return 'video'
  if (/son|audio|musique/.test(label)) return 'audio'
  return 'file'
}
// Vignette réelle quand elle est disponible ; sinon tuile avec l'icône du format.
function showsImage(item) {
  return THUMBNAILED.includes(kind(item)) && Boolean(sources.value[item.id])
}
function showsError(item) {
  return kind(item) === 'image' && Boolean(errors.value[item.id])
}
function loading(item) {
  return THUMBNAILED.includes(kind(item)) && !sources.value[item.id] && !errors.value[item.id]
}
function extensionLabel(item) {
  return (item.extension || '').toUpperCase()
}
onMounted(async () => {
  await Promise.all(items.value.filter(item => THUMBNAILED.includes(kind(item))).map(async item => {
    try {
      // Vignette légère ; l'original n'est chargé qu'à l'ouverture de l'aperçu.
      const blob = await api(`/materials/${item.id}/thumbnail`, { responseType: 'blob' })
      if (disposed) return
      if (!blob.type.startsWith('image/')) throw new Error('Format de fichier incompatible avec ce type de média.')
      sources.value[item.id] = URL.createObjectURL(blob)
    } catch (error) {
      if (!disposed) errors.value[item.id] = error.message
    }
  }))
})
onBeforeUnmount(() => {
  disposed = true
  Object.values(sources.value).forEach(source => URL.revokeObjectURL(source))
})
</script>
<template>
  <div v-if="items.length" class="sequence-images">
    <figure v-for="item in items" :key="item.id">
      <p v-if="showsError(item)" role="alert">{{ errors[item.id] }}</p>
      <p v-else-if="loading(item)" role="status">Chargement…</p>
      <MediaPreview
        v-else-if="PREVIEWABLE.includes(kind(item))"
        :id="item.id"
        icon
        class="thumbnail-preview"
      >
        <span v-if="showsImage(item)" :class="['video-thumbnail', `thumbnail-${kind(item)}`]">
          <img :src="sources[item.id]" :alt="item.nom" />
          <span v-if="kind(item) === 'video'" class="play-badge" aria-hidden="true" />
          <span v-else-if="kind(item) === 'pdf'" class="media-badge pdf-badge" aria-hidden="true">
            <FileTypeIcon kind="pdf" :size="14" />PDF
          </span>
          <span v-else-if="['presentation', 'document'].includes(kind(item))" :class="['media-badge', `${kind(item)}-badge`]" aria-hidden="true">
            <FileTypeIcon :kind="kind(item)" :size="14" />{{ extensionLabel(item) }}
          </span>
          <span v-else-if="kind(item) === 'image'" class="media-badge image-badge" aria-hidden="true">
            <FileTypeIcon kind="image" :size="14" />
          </span>
        </span>
        <span v-else :class="['file-tile', `file-tile--${kind(item)}`]">
          <FileTypeIcon v-if="kind(item) !== 'video'" :kind="kind(item)" />
          <span v-else class="play-badge" aria-hidden="true" />
          <span v-if="extensionLabel(item)" class="file-ext">{{ extensionLabel(item) }}</span>
        </span>
      </MediaPreview>
      <NuxtLink v-else :to="`/materials/${item.id}`" class="file-tile-link">
        <span :class="['file-tile', `file-tile--${kind(item)}`]">
          <FileTypeIcon :kind="kind(item)" />
          <span v-if="extensionLabel(item)" class="file-ext">{{ extensionLabel(item) }}</span>
        </span>
      </NuxtLink>
      <figcaption>
        <NuxtLink :to="`/materials/${item.id}`">{{ item.nom }}</NuxtLink>
        <DownloadButton
          :path="`/materials/${item.id}/file`"
          icon="download"
          :label="`Télécharger ${item.nom}`"
        />
      </figcaption>
    </figure>
  </div>
</template>
