<script setup>
import { useSessionStore } from '~/stores/session'
import { materialFields, materialPayload } from '../../lib/forms.mjs'
const props = defineProps({
  id: [String, Number],
  icon: Boolean,
  // Affiche à droite du média ses informations, modifiables par un administrateur.
  details: Boolean
})
const emit = defineEmits(['updated', 'deleted'])
const api = useApi()
const config = useRuntimeConfig()
const session = useSessionStore()
const catalog = useCatalog()
const draft = ref(null)
const saving = ref(false)
const saved = ref(false)
const form_error = ref('')
async function loadDetails() {
  if (!props.details) return
  try {
    await catalog.load()
    draft.value = structuredClone(toRaw(await api(`/materials/${props.id}`)))
  } catch (e) {
    form_error.value = e.message
  }
}
async function save() {
  saving.value = true
  saved.value = false
  form_error.value = ''
  try {
    draft.value = structuredClone(
      toRaw(
        await api(`/materials/${props.id}`, {
          method: 'PUT',
          body: materialPayload(draft.value)
        })
      )
    )
    saved.value = true
    emit('updated', draft.value)
  } catch (e) {
    form_error.value = e.message
  } finally {
    saving.value = false
  }
}
async function remove() {
  if (!window.confirm('Supprimer cette notice et détacher ses associations ?'))
    return
  try {
    await api(`/materials/${props.id}`, { method: 'DELETE' })
    dialog.value.close()
    emit('deleted', props.id)
  } catch (e) {
    error.value = e.message
  }
}
const dialog = ref(null)
const source = ref('')
const mime = ref('')
const error = ref('')
const busy = ref(false)
const converted = ref(false)
async function preview() {
  converted.value = false
  dialog.value.showModal()
  // Évite que le premier bouton (et son infobulle) prenne le focus à l'ouverture.
  dialog.value.focus()
  saved.value = false
  form_error.value = ''
  loadDetails()
  await load(false)
}
// Essaie d'abord la lecture native (aucune conversion côté serveur) ;
// si le navigateur ne sait pas lire le média, on redemande une copie convertie.
async function load(convert) {
  busy.value = true
  error.value = ''
  try {
    const url = `${config.public.apiBase}/materials/${props.id}/preview${convert ? '' : '?natif=1'}`
    const controller = new AbortController()
    const response = await fetch(url, {
      credentials: 'include',
      signal: controller.signal
    })
    if (!response.ok) {
      let detail = null
      try {
        detail = (await response.json()).error?.message
      } catch {}
      throw new Error(detail || 'Le service est inaccessible. Réessayez.')
    }
    const type = (response.headers.get('content-type') || '').split(';')[0]
    if (!dialog.value?.open) return controller.abort()
    if (
      !/^(image\/(png|jpeg|gif|webp)|audio\/|video\/|application\/pdf)/.test(
        type
      )
    )
      throw new Error(
        'Aperçu indisponible pour ce format. Utilisez le téléchargement.'
      )
    if (source.value && source.value.startsWith('blob:'))
      URL.revokeObjectURL(source.value)
    mime.value = type
    if (/^(audio|video)\//.test(type)) {
      // Lecture en flux : le navigateur demande seulement les octets utiles.
      controller.abort()
      source.value = url
    } else {
      source.value = URL.createObjectURL(await response.blob())
    }
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}
function playback_failed(kind) {
  if (!converted.value) {
    converted.value = true
    source.value = ''
    return load(true)
  }
  error.value = `Ce navigateur ne peut pas lire ${kind}. Utilisez le téléchargement.`
}
defineExpose({ preview })
function close() {
  if (source.value.startsWith('blob:')) URL.revokeObjectURL(source.value)
  source.value = ''
}
onBeforeUnmount(() => {
  if (source.value.startsWith('blob:')) URL.revokeObjectURL(source.value)
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
      @click="preview()"
      ><slot><ActionIcon v-if="icon" name="preview" /></slot></PButton>
    <dialog
      ref="dialog"
      tabindex="-1"
      class="preview-dialog"
      aria-label="Aperçu de la pièce jointe"
      @close="close"
      @click="$event.target === dialog && dialog.close()"
    >
      <div class="toolbar">
        <h2>Aperçu de la pièce jointe</h2>
        <div class="dialog-actions">
          <DownloadButton
            :path="`/materials/${id}/file`"
            icon="download"
            label="Télécharger le média"
            data-tooltip="Télécharger le média"
          />
          <PButton
            v-if="details && session.is_admin"
            type="button"
            class="danger icon-button"
            aria-label="Supprimer le média"
            data-tooltip="Supprimer le média"
            @click="remove"
            ><ActionIcon name="delete"
          /></PButton>
        </div>
        <div class="dialog-actions">
          <PButton
            type="button"
            class="icon-button close-button"
            aria-label="Fermer"
            data-tooltip="Fermer"
            @click="dialog.close()"
            ><ActionIcon name="close"
          /></PButton>
        </div>
      </div>
      <p v-if="busy" role="status">Préparation de l’aperçu…</p>
      <p v-if="error" role="alert" class="error">{{ error }}</p>
      <div :class="{ 'preview-layout': details }">
      <div v-if="source" class="media-preview">
        <img
          v-if="mime.startsWith('image/')"
          :src="source"
          alt="Pièce jointe de la ressource"
        />
        <audio
          v-else-if="mime.startsWith('audio/')"
          :src="source"
          controls
          @error="playback_failed('ce fichier audio (format non pris en charge)')"
        />
        <video
          v-else-if="mime.startsWith('video/')"
          :src="source"
          controls
          @error="playback_failed('cette vidéo (format ou codec non pris en charge)')"
        />
        <iframe v-else :src="source" title="Aperçu du document PDF" />
      </div>
      <form
        v-if="details && draft"
        class="media-details"
        @submit.prevent="save"
      >
        <h3>Informations sur le média</h3>
        <p v-if="form_error" role="alert" class="error">{{ form_error }}</p>
        <p v-if="saved" role="status">Modifications enregistrées.</p>
        <fieldset :disabled="saving || !session.is_admin">
          <label
            >Nom *<input v-model="draft.nom" required maxlength="100"
          /></label>
          <RefSelect
            v-model="draft.fk_type_mat_id"
            :items="catalog.family('ref.type_mat')"
            label="Type *"
            required
          />
          <TextFields v-model="draft" :fields="materialFields" />
          <label
            >Localisation<input v-model="draft.localisation" maxlength="50"
          /></label>
          <TagPicker
            v-model="draft.thematiques"
            :items="catalog.family('ref.thematiques')"
            legend="Thématiques"
          />
          <PButton
            v-if="session.is_admin"
            type="submit"
            label="Modifier"
            :disabled="saving"
          />
        </fieldset>
      </form>
      </div>
    </dialog>
  </span>
</template>
