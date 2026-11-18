<script setup>
const props = defineProps({
  items: { type: Array, required: true },
  // Ressource de l'API : '/media' ou '/outils'.
  base: { type: String, default: '/media' },
  // Vignettes seules, sans légende.
  bare: Boolean,
  editable: Boolean,
  // Mode choix : la vignette est un bouton qui sélectionne le média.
  selectable: Boolean,
  // Fenêtre d'aperçu avec le formulaire d'informations du média.
  details: Boolean,
  // Critères de la liste filtrée, pour naviguer entre médias dans l'aperçu.
  query: { type: Object, default: null }
})
const emit = defineEmits(['remove', 'select', 'updated', 'deleted'])
const api = useApi()
const catalog = useCatalog()
const sources = ref({})
const errors = ref({})
// Fenêtres d'aperçu par média, pour ouvrir l'aperçu depuis le titre.
const previews = {}
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
  const label = catalog.label(item.fk_type_mat_id || item.fk_type_mat_outil_id).toLocaleLowerCase()
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
async function loadThumbnails() {
  await Promise.all(items.value.filter(item => THUMBNAILED.includes(kind(item)) && !sources.value[item.id] && !errors.value[item.id]).map(async item => {
    try {
      // Vignette légère ; l'original n'est chargé qu'à l'ouverture de l'aperçu.
      const blob = await api(`${props.base}/${item.id}/thumbnail`, { responseType: 'blob' })
      if (disposed) return
      if (!blob.type.startsWith('image/')) throw new Error('Format de fichier incompatible avec ce type de média.')
      sources.value[item.id] = URL.createObjectURL(blob)
    } catch (error) {
      if (!disposed) errors.value[item.id] = error.message
    }
  }))
}
onMounted(loadThumbnails)
watch(() => items.value.map(item => item.id).join(','), loadThumbnails)
onBeforeUnmount(() => {
  disposed = true
  Object.values(sources.value).forEach(source => URL.revokeObjectURL(source))
})
</script>
<template>
  <div v-if="items.length || editable" class="sequence-images">
    <figure v-for="item in items" :key="item.id">
      <p v-if="showsError(item)" role="alert">{{ errors[item.id] }}</p>
      <p v-else-if="loading(item)" role="status">Chargement…</p>
      <span v-else-if="selectable" class="selectable-thumb">
        <MediaPreview
          v-if="PREVIEWABLE.includes(kind(item))"
          :id="item.id"
          icon
          class="thumbnail-preview"
        >
          <MediaTile :item="item" :kind="kind(item)" :source="sources[item.id]" :image="showsImage(item)" :extension="extensionLabel(item)" />
        </MediaPreview>
        <span v-else class="thumbnail-preview">
          <MediaTile :item="item" :kind="kind(item)" :source="sources[item.id]" :image="showsImage(item)" :extension="extensionLabel(item)" />
        </span>
        <button
          type="button"
          class="add-media-button"
          data-tooltip="Ajouter le média"
          :aria-label="`Ajouter le média ${item.nom}`"
          @click="emit('select', item)"
        >
          <ActionIcon name="add" />
        </button>
      </span>
      <MediaPreview
        v-else-if="PREVIEWABLE.includes(kind(item))"
        :id="item.id"
        :base="base"
        icon
        :ref="(component) => (previews[item.id] = component)"
        :details="details"
        :query="query"
        class="thumbnail-preview"
        @updated="emit('updated', $event)"
        @deleted="emit('deleted', $event)"
      >
        <MediaTile :item="item" :kind="kind(item)" :source="sources[item.id]" :image="showsImage(item)" :extension="extensionLabel(item)" />
      </MediaPreview>
      <NuxtLink v-else :to="`/materials/${item.id}`" class="file-tile-link">
        <span :class="['file-tile', `file-tile--${kind(item)}`]">
          <FileTypeIcon :kind="kind(item)" />
          <span v-if="extensionLabel(item)" class="file-ext">{{ extensionLabel(item) }}</span>
        </span>
      </NuxtLink>
      <figcaption v-if="selectable">{{ item.nom }}</figcaption>
      <figcaption v-else-if="!bare">
        <a
          v-if="details && PREVIEWABLE.includes(kind(item))"
          href="#"
          @click.prevent="previews[item.id]?.preview()"
          >{{ item.nom }}</a
        >
        <NuxtLink v-else :to="`/materials/${item.id}`">{{ item.nom }}</NuxtLink>
        <DownloadButton
          :path="`${base}/${item.id}/file`"
          icon="download"
          :label="`Télécharger ${item.nom}`"
        />
        <PButton
          v-if="editable"
          type="button"
          class="icon-button secondary danger-icon"
          :aria-label="`Retirer ${item.nom}`"
          title="Retirer ce média"
          @click="emit('remove', item.id)"
          ><ActionIcon name="close"
        /></PButton>
      </figcaption>
    </figure>
    <slot />
  </div>
</template>
