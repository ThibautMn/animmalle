<script setup>
import { useSessionStore } from '~/stores/session'
import {
  mediaFields,
  mediaPayload,
  outilFields,
  outilPayload
} from '../../../lib/forms.mjs'
const route = useRoute()
// Même identifiant possible pour un média et un outil : recharger la page quand le type change.
definePageMeta({ key: (route) => route.fullPath })
const api = useApi()
const session = useSessionStore()
const catalog = useCatalog()
const creating = route.params.id === 'nouveau'
// Les médias et les outils facilitateurs sont deux ressources distinctes de l'API.
const kind = route.query.kind === 'outil' ? 'outil' : 'media'
const tool = kind === 'outil'
const base = tool ? '/outils' : '/media'
const fields = tool ? outilFields : mediaFields
const payloadOf = tool ? outilPayload : mediaPayload
const typeKey = tool ? 'fk_type_outil_id' : 'fk_type_mat_id'
const item = ref(
  tool
    ? {
        nom: '',
        fk_type_outil_id: null,
        description: '',
        variante: '',
        difficulte_id: null,
        materiel: '',
        fk_type_mat_outil_id: null
      }
    : { nom: '', fk_type_mat_id: null, description: '', thematiques: [] }
)
const draft = ref(null)
const file = ref(null)
const editing = ref(creating || (session.is_admin && route.query.edit === '1'))
const busy = ref(true)
const error = ref('')
const path = `${base}/${route.params.id}`
async function load() {
  busy.value = true
  error.value = ''
  try {
    await catalog.load()
    if (!creating) {
      item.value = await api(path)
    }
    draft.value = structuredClone(toRaw(item.value))
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}
async function save() {
  busy.value = true
  error.value = ''
  try {
    let result
    if (creating) {
      const body = new FormData()
      body.append('data', JSON.stringify(payloadOf(draft.value)))
      if (file.value) body.append('file', file.value)
      result = await api(base, { method: 'POST', body })
      editing.value = false
      await navigateTo(`/materials/${result.id}?kind=${kind}`)
    } else {
      result = await api(path, {
        method: 'PUT',
        body: payloadOf(draft.value)
      })
      // Conserver le formulaire si le remplacement du fichier échoue après la notice.
      item.value = result
      if (file.value) {
        const body = new FormData()
        body.append('file', file.value)
        await api(`${path}/file`, { method: 'POST', body })
      }
      file.value = null
      editing.value = false
      await load()
    }
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}
async function remove() {
  if (!window.confirm('Supprimer cette notice et détacher ses associations ?'))
    return
  busy.value = true
  error.value = ''
  try {
    await api(path, { method: 'DELETE' })
    await navigateTo(tool ? '/outils' : '/materials')
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}
function cancel() {
  editing.value = false
  file.value = null
  draft.value = structuredClone(toRaw(item.value))
}
onBeforeRouteLeave(
  () =>
    !editing.value ||
    window.confirm('Quitter sans enregistrer les modifications ?')
)
onMounted(load)
</script>
<template>
  <NuxtLink :to="tool ? '/outils' : '/materials'"
    >← Retour aux ressources</NuxtLink
  >
  <p v-if="error" role="alert" class="error">{{ error }}</p>
  <p v-if="busy" role="status">Chargement…</p>
  <template v-if="draft"
    ><form v-if="editing" @submit.prevent="save">
      <h1>
        {{ creating ? 'Importer une ressource' : 'Modifier la ressource' }}
      </h1>
      <fieldset :disabled="busy">
        <label
          >Nom *<input v-model="draft.nom" required maxlength="100" /></label
        ><RefSelect
          v-model="draft[typeKey]"
          :items="catalog.family(tool ? 'ref.type_outil' : 'ref.type_mat')"
          label="Type *"
          required
        /><TextFields v-model="draft" :fields="fields" /><template
          v-if="tool"
          ><RefSelect
            v-model="draft.difficulte_id"
            :items="catalog.family('ref.difficulte')"
            label="Difficulté" /><RefSelect
            v-model="draft.fk_type_mat_outil_id"
            :items="catalog.family('ref.type_mat')"
            label="Type de pièce jointe" /></template
        ><TagPicker
          v-if="!tool"
          v-model="draft.thematiques"
          :items="catalog.family('ref.thematiques')"
          legend="Thématiques"
        /><label
          >Pièce jointe<input
            type="file"
            @change="file = $event.target.files[0] || null"
        /></label>
        <p v-if="!creating && file">
          La notice est enregistrée avant le remplacement du fichier ; vous
          pourrez réessayer si le transfert échoue.
        </p>
        <PButton type="submit" label="Enregistrer" /><PButton
          v-if="!creating"
          type="button"
          class="secondary"
          label="Annuler"
          @click="cancel"
        />
      </fieldset>
    </form>
    <template v-else
      ><div class="toolbar">
        <h1>{{ item.nom }}</h1>
        <span class="badge">{{ catalog.label(item[typeKey]) }}</span>
      </div>
      <p>{{ item.date_modif }}</p>
      <div class="actions">
        <DownloadButton
          :path="`${path}/download`"
          :filename="`${item.nom}.zip`"
          label="Exporter en ZIP / ODT"
        /><DownloadButton
          v-if="item.has_file"
          :path="`${path}/file`"
          label="Télécharger la pièce jointe"
        /><PButton
          v-if="session.is_admin"
          label="Modifier"
          @click="editing = true"
        /><PButton
          v-if="session.is_admin"
          class="danger"
          label="Supprimer"
          :disabled="busy"
          @click="remove"
        />
      </div>
      <MediaPreview v-if="item.has_file && !tool" :id="item.id" />
      <section v-for="[key, label] in fields" :key="key" class="card">
        <h2>{{ label }}</h2>
        <RichText v-if="item[key]" :text="item[key]" /><p v-else class="prose">Non renseigné</p>
      </section>
      <p v-if="tool">
        Difficulté : {{ catalog.label(item.difficulte_id) || 'Non renseignée' }}
      </p>
      <p v-if="!tool" class="pictos">
        <PictoIcon
          v-for="tag in item.thematiques"
          :id="tag"
          :key="tag"
          :size="40"
        />
      </p>
      <p v-if="!tool">
        {{ item.thematiques.map(catalog.label).join(' · ') }}
      </p></template
    ></template
  >
</template>
