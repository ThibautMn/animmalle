<script setup>
const props = defineProps({ id: [String, Number], icon: Boolean })
const api = useApi()
const dialog = ref(null)
const source = ref('')
const mime = ref('')
const error = ref('')
const busy = ref(false)
async function preview() {
  dialog.value.showModal()
  busy.value = true
  error.value = ''
  try {
    const blob = await api(`/materials/${props.id}/preview`, {
      responseType: 'blob'
    })
    if (!dialog.value?.open) return
    mime.value = blob.type
    if (
      !/^(image\/(png|jpeg|gif|webp)|audio\/|video\/|application\/pdf)/.test(
        blob.type
      )
    )
      throw new Error(
        'Aperçu indisponible pour ce format. Utilisez le téléchargement.'
      )
    if (source.value) URL.revokeObjectURL(source.value)
    source.value = URL.createObjectURL(blob)
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}
function close() {
  if (source.value) URL.revokeObjectURL(source.value)
  source.value = ''
}
onBeforeUnmount(() => {
  if (source.value) URL.revokeObjectURL(source.value)
})
</script>
<template>
  <span>
    <PButton
      type="button"
      :label="icon ? undefined : 'Aperçu de la pièce jointe'"
      aria-label="Aperçu de la pièce jointe"
      title="Aperçu de la pièce jointe"
      :class="{ 'icon-button': icon }"
      :disabled="busy"
      @click="preview"
      ><slot><ActionIcon v-if="icon" name="preview" /></slot></PButton>
    <dialog
      ref="dialog"
      class="preview-dialog"
      aria-label="Aperçu de la pièce jointe"
      @close="close"
      @click="$event.target === dialog && dialog.close()"
    >
      <div class="toolbar">
        <h2>Aperçu de la pièce jointe</h2>
        <PButton label="Fermer" @click="dialog.close()" />
      </div>
      <p v-if="busy" role="status">Préparation de l’aperçu…</p>
      <p v-if="error" role="alert" class="error">{{ error }}</p>
      <div v-if="source" class="media-preview">
        <img
          v-if="mime.startsWith('image/')"
          :src="source"
          alt="Pièce jointe de la ressource"
        />
        <audio v-else-if="mime.startsWith('audio/')" :src="source" controls />
        <video
          v-else-if="mime.startsWith('video/')"
          :src="source"
          controls
          @error="error = 'Ce navigateur ne peut pas lire cette vidéo (format ou codec non pris en charge). Utilisez le téléchargement.'"
        />
        <iframe v-else :src="source" title="Aperçu du document PDF" />
      </div>
    </dialog>
  </span>
</template>
