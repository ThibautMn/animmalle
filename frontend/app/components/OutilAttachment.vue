<script setup>
// Pièce jointe d'un outil en édition : vignette (fichier enregistré ou fichier choisi, avant
// enregistrement) ; un clic ouvre la fenêtre de remplacement.
const props = defineProps({
  item: { type: Object, required: true },
  file: { type: Object, default: null }
})
const emit = defineEmits(['edit', 'clear'])
const api = useApi()
const source = ref('')
const failed = ref(false)
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
const extension = computed(() =>
  (props.file ? props.file.name.split('.').pop() : props.item.extension || '').toLowerCase()
)
const kind = computed(
  () => Object.keys(EXTENSIONS).find((name) => EXTENSIONS[name].includes(extension.value)) || 'file'
)
const name = computed(() => props.file?.name || props.item.nom)
let url = ''
function release() {
  if (url) URL.revokeObjectURL(url)
  url = ''
  source.value = ''
}
async function refresh() {
  release()
  failed.value = false
  if (props.file) {
    // Aperçu immédiat du fichier choisi : image, ou première page d'un PDF via le lecteur du navigateur.
    if (kind.value === 'image' || kind.value === 'pdf') source.value = url = URL.createObjectURL(props.file)
    return
  }
  if (!props.item.has_file) return
  try {
    const blob = await api(`/outils/${props.item.id}/thumbnail`, { responseType: 'blob' })
    if (!blob.type.startsWith('image/')) throw new Error('Format incompatible')
    source.value = url = URL.createObjectURL(blob)
  } catch {
    failed.value = true
  }
}
watch(() => [props.file, props.item.has_file, props.item.id], refresh, { immediate: true })
onBeforeUnmount(release)
</script>
<template>
  <figure class="outil-attachment">
    <button type="button" class="outil-attachment-button" @click="emit('edit')">
      <span v-if="file && kind === 'pdf' && source" class="video-thumbnail thumbnail-pdf pdf-live">
        <iframe :src="`${source}#toolbar=0&navpanes=0&scrollbar=0&view=FitH`" :title="name" tabindex="-1" />
        <span class="media-badge pdf-badge" aria-hidden="true"><FileTypeIcon kind="pdf" :size="14" />PDF</span>
      </span>
      <MediaTile
        v-else
        :item="{ nom: name }"
        :kind="kind"
        :source="source"
        :image="Boolean(source)"
        :extension="extension.toUpperCase()"
      />
      <span class="outil-attachment-hover">
        <i class="pi pi-pencil" aria-hidden="true" />
        <span>Remplacer le média</span>
      </span>
    </button>
    <figcaption v-if="file">
      Nouveau fichier : <strong>{{ file.name }}</strong>
      <PButton
        type="button"
        class="icon-button secondary danger-icon"
        :aria-label="`Annuler le remplacement par ${file.name}`"
        title="Annuler"
        @click="emit('clear')"
        ><ActionIcon name="close"
      /></PButton>
    </figcaption>
  </figure>
</template>
