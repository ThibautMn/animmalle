<script setup>
import { useSessionStore } from '~/stores/session'
import { toPlainText } from '../../../lib/richtext.mjs'
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
const neighbors = ref(null)
const outilSearch = useState('outil_search', () => null)
const file = ref(null)
const fileDialog = ref(null)
function pickFile({ file: picked, typeId }) {
  file.value = picked
  draft.value.fk_type_mat_outil_id = typeId
}
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
    if (tool && !creating) loadNeighbors()
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}
async function loadNeighbors() {
  try {
    const fetchNeighbors = (query) =>
      api(`${path}/neighbors`, { query, retry: 0 })
    let result = await fetchNeighbors(outilSearch.value || {})
    // Fiche absente de la dernière recherche : on revient à la liste complète
    if (!result.found && outilSearch.value) {
      outilSearch.value = null
      result = await fetchNeighbors({})
    }
    neighbors.value = result.found ? result : null
  } catch {
    neighbors.value = null
  }
}
async function save() {
  busy.value = true
  error.value = ''
  try {
    // Sans pièce jointe, le type de pièce jointe n'a pas de sens (et peut être une valeur historique invalide).
    if (tool && !file.value && !item.value.has_file)
      draft.value.fk_type_mat_outil_id = null
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
const { confirmDelete } = useConfirmDelete()
async function remove() {
  if (!(await confirmDelete(`Supprimer ${tool ? 'cet outil' : 'ce média'} et détacher ses associations ?`)))
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
  <nav v-if="tool && neighbors && !editing" class="fiche-nav" aria-label="Outils voisins">
    <NuxtLink
      v-if="neighbors.previous"
      class="nav-arrow nav-prev"
      :to="`/materials/${neighbors.previous.id}?kind=outil`"
      :aria-label="`Outil précédent : ${neighbors.previous.nom}`"
      :data-tooltip="`Passe à l'outil précédent : ${neighbors.previous.nom}`"
      >‹</NuxtLink
    >
    <NuxtLink
      v-if="neighbors.next"
      class="nav-arrow nav-next"
      :to="`/materials/${neighbors.next.id}?kind=outil`"
      :aria-label="`Outil suivant : ${neighbors.next.nom}`"
      :data-tooltip="`Passe à l'outil suivant : ${neighbors.next.nom}`"
      >›</NuxtLink
    >
  </nav>
  <p v-if="error" role="alert" class="error">{{ error }}</p>
  <p v-if="busy" role="status">Chargement…</p>
  <template v-if="draft"
    ><form v-if="editing && tool" @submit.prevent="save">
      <fieldset :disabled="busy" class="tool-edit">
        <div class="tool-sheet tools-tint">
          <header class="toolbar tool-header">
            <div class="tool-title tool-title-edit">
              <div class="tool-name-row">
                <input
                  v-model="draft.nom"
                  class="tool-name-input"
                  required
                  maxlength="100"
                  placeholder="Nom de l’outil"
                  aria-label="Nom de l’outil (obligatoire)"
                /><span class="required-mark" aria-hidden="true">*</span>
              </div>
              <div class="tool-refs">
                <RefSelect
                  v-model="draft.fk_type_outil_id"
                  :items="catalog.family('ref.type_outil')"
                  label="Type *"
                  required
                /><RefSelect
                  v-model="draft.difficulte_id"
                  :items="catalog.family('ref.difficulte')"
                  label="Difficulté"
                />
              </div>
            </div>
          </header>
          <div class="tool-body">
            <div class="tool-main">
              <fieldset
                v-for="[key, label] in fields.filter(([key]) => key !== 'materiel')"
                :key="key"
                :class="['tool-block', key === 'variante' && 'tool-block-variante']"
              >
                <legend>{{ label }}</legend>
                <RichEditor v-model="draft[key]" :label="label" />
              </fieldset>
            </div>
            <aside class="tool-side">
              <OutilAttachment
                v-if="item.has_file || file"
                :item="item"
                :file="file"
                @edit="fileDialog.open()"
                @clear="file = null"
              />
              <figure v-else class="media-add">
                <button
                  type="button"
                  class="media-add-tile"
                  data-tooltip="Choisit un fichier ou un média de la bibliothèque à joindre à l'outil"
                  @click="fileDialog.open()"
                >
                  <ActionIcon name="add" />
                  <span>Ajouter un média</span>
                </button>
              </figure>
              <fieldset class="tool-block tool-block-materiel">
                <legend>Matériel</legend>
                <RichEditor v-model="draft.materiel" label="Matériel" simple />
              </fieldset>
            </aside>
          </div>
        </div>
        <p v-if="!creating && file">
          La notice est enregistrée avant le remplacement du fichier ; vous
          pourrez réessayer si le transfert échoue.
        </p>
        <PButton
          type="submit"
          label="Enregistrer"
          data-tooltip="Enregistre les modifications de la fiche"
        /><PButton
          v-if="!creating"
          type="button"
          class="secondary"
          label="Annuler"
          data-tooltip="Abandonne les modifications et revient à la fiche"
          @click="cancel"
        />
      </fieldset>
    </form>
    <form v-else-if="editing" @submit.prevent="save">
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
        <div class="tip-above tip-start form-buttons"><PButton
          type="submit"
          label="Enregistrer"
          data-tooltip="Enregistre les modifications de la ressource"
        /><PButton
          v-if="!creating"
          type="button"
          class="secondary"
          label="Annuler"
          data-tooltip="Abandonne les modifications et revient à la fiche"
          @click="cancel"
        /></div>
      </fieldset>
    </form>
    <template v-else
      ><div
        :class="[
          'actions actions-end',
          tool && (item.has_file || toPlainText(item.materiel)) && 'actions-narrow'
        ]"
      >
        <PButton
          v-if="session.is_admin"
          label="Modifier"
          data-tooltip="Passe la fiche en mode modification"
          @click="editing = true"
        /><DownloadButton
          :path="`${path}/download`"
          :filename="`${item.nom}.zip`"
          label="Télécharger le kit"
          data-tooltip="Télécharge l'outil et ses fichiers dans une archive ZIP"
          icon="pi-box"
          show-label
        /><PButton
          v-if="session.is_admin"
          class="danger icon-button"
          aria-label="Supprimer"
          data-tooltip="Supprime définitivement l'outil après confirmation"
          :disabled="busy"
          @click="remove"
          ><ActionIcon name="delete"
        /></PButton>
      </div>
      <OutilSheet v-if="tool" :item="item" />
      <template v-else
        ><header :class="['toolbar', tool && 'tool-header']">
        <div class="tool-title">
          <h1>{{ item.nom }}</h1>
          <small v-if="tool" class="muted"
            >Modifiée le {{ item.date_modif || '—' }}</small
          >
          <p v-else>{{ item.date_modif }}</p>
        </div>
        <span class="tool-badges">
          <span class="badge">{{ catalog.label(item[typeKey]) }}</span>
          <span v-if="tool && catalog.label(item.difficulte_id)" class="badge">{{
            catalog.label(item.difficulte_id)
          }}</span>
        </span>
      </header><MediaPreview v-if="item.has_file" :id="item.id" />
        <section v-for="[key, label] in fields" :key="key" class="card">
          <h2>{{ label }}</h2>
          <RichText v-if="item[key]" :text="item[key]" /><p
            v-else
            class="prose"
          >
            Non renseigné
          </p>
        </section>
        <p class="pictos">
          <PictoIcon
            v-for="tag in item.thematiques"
            :id="tag"
            :key="tag"
            :size="40"
          />
        </p>
        <p>{{ item.thematiques.map(catalog.label).join(' · ') }}</p></template
      ></template
    ></template
  >
  <MediaAddDialog
    v-if="tool && draft"
    ref="fileDialog"
    tool
    :type-id="draft.fk_type_mat_outil_id"
    @pick-file="pickFile"
  />
</template>
