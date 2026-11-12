<script setup>
const props = defineProps({ item: Object })
const version = useState('picto_version', () => 0)
const api = useApi()
const dialog = ref(null)
const input = ref(null)
const config = useRuntimeConfig()
const busy = ref(false)
const error = ref('')
const preview = ref('')
const file = ref(null)
function open() {
  error.value = ''
  clear()
  dialog.value.showModal()
}
function clear() {
  if (preview.value) URL.revokeObjectURL(preview.value)
  preview.value = ''
  file.value = null
  if (input.value) input.value.value = ''
}
function choose(event) {
  const chosen = event.target.files[0]
  clear()
  if (!chosen) return
  if (chosen.type !== 'image/png') {
    error.value = 'Le pictogramme doit être une image PNG.'
    return
  }
  error.value = ''
  file.value = chosen
  preview.value = URL.createObjectURL(chosen)
}
async function save() {
  busy.value = true
  error.value = ''
  try {
    const body = new FormData()
    body.append('file', file.value)
    await api(`/thesaurus/${props.item.id}/pictogram`, { method: 'PUT', body })
    version.value++
    dialog.value.close()
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}
async function remove() {
  if (!window.confirm(`Supprimer le pictogramme de « ${props.item.label} » ?`))
    return
  busy.value = true
  error.value = ''
  try {
    await api(`/thesaurus/${props.item.id}/pictogram`, { method: 'DELETE' })
    version.value++
    dialog.value.close()
  } catch (e) {
    error.value =
      e.status === 404 ? 'Ce terme n’a pas de pictogramme.' : e.message
  } finally {
    busy.value = false
  }
}
onBeforeUnmount(clear)
</script>
<template>
  <span>
    <PButton
      class="bare-icon"
      type="button"
      title="Pictogramme"
      :aria-label="`Pictogramme de ${item.label}`"
      @click="open"
      ><ActionIcon name="image"
    /></PButton>
    <dialog
      ref="dialog"
      class="preview-dialog picto-dialog"
      :aria-label="`Pictogramme de ${item.label}`"
      @close="clear"
      @click="$event.target === dialog && dialog.close()"
    >
      <div class="toolbar">
        <h2>Pictogramme · {{ item.label }}</h2>
        <PButton
          class="bare-icon"
          type="button"
          title="Fermer"
          aria-label="Fermer"
          @click="dialog.close()"
          ><ActionIcon name="close"
        /></PButton>
      </div>
      <p v-if="error" role="alert" class="error">{{ error }}</p>
      <div class="picto-current">
        <figure>
          <PictoIcon :id="item.id" :size="96" />
          <figcaption>Actuel</figcaption>
        </figure>
        <figure v-if="preview">
          <img :src="preview" alt="Nouveau pictogramme" width="96" height="96" />
          <figcaption>Nouveau</figcaption>
        </figure>
      </div>
      <label
        >Image PNG (1 Mo maximum)<input
          ref="input"
          type="file"
          accept="image/png"
          :disabled="busy"
          @change="choose"
      /></label>
      <div class="actions">
        <PButton
          type="button"
          label="Enregistrer"
          :disabled="busy || !file"
          @click="save"
        />
        <PButton
          type="button"
          class="danger"
          label="Retirer le pictogramme"
          :disabled="busy"
          @click="remove"
        />
      </div>
    </dialog>
  </span>
</template>
<style scoped>
.toolbar {
  align-items: center;
}

.toolbar h2 {
  flex: 1;
  margin: 0;
}

.picto-dialog {
  width: min(460px, 92vw);
}
.picto-current {
  display: flex;
  gap: 24px;
  margin: 12px 0;
}
.picto-current figure {
  margin: 0;
  text-align: center;
}
.picto-current img {
  object-fit: contain;
}
</style>
