<script setup>
const props = defineProps({ id: [String, Number] })
const api = useApi()
const source = ref('')
const mime = ref('')
const error = ref('')
const busy = ref(false)
async function preview() {
  busy.value = true
  error.value = ''
  try {
    const blob = await api(`/materials/${props.id}/file`, {
      responseType: 'blob'
    })
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
onBeforeUnmount(() => {
  if (source.value) URL.revokeObjectURL(source.value)
})
</script>
<template>
  <section>
    <PButton
      label="Aperçu de la pièce jointe"
      :disabled="busy"
      @click="preview"
    />
    <p v-if="error" role="alert">{{ error }}</p>
    <div v-if="source" class="media-preview">
      <img
        v-if="mime.startsWith('image/')"
        :src="source"
        alt="Pièce jointe de la ressource"
      /><audio
        v-else-if="mime.startsWith('audio/')"
        :src="source"
        controls
      /><video
        v-else-if="mime.startsWith('video/')"
        :src="source"
        controls
      /><iframe
        v-else
        :src="source"
        title="Aperçu du document PDF"
        sandbox=""
      />
    </div>
  </section>
</template>
