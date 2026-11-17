<script setup>
import { useSessionStore } from '~/stores/session'
import {
  animationFields,
  sequenceFields,
  sequenceRefs,
  newSequence,
  formatMinutes,
  animationPayload,
  moveSequence,
} from '../../../lib/forms.mjs'
const window = globalThis.window
const route = useRoute()
const api = useApi()
const session = useSessionStore()
const catalog = useCatalog()
const creating = route.params.id === 'nouveau'
const item = ref({
  titre: '',
  statut: 3,
  lieu: '',
  fk_duree_id: null,
  tags: [],
  sequences: [],
  ...Object.fromEntries(animationFields.map(([key]) => [key, ''])),
})
const draft = ref(null)
const comments = ref([])
const comment = ref('')
const author = ref('')
const suggestions = ref([])
const mediaItems = ref({})
const error = ref('')
const neighbors = ref(null)
const animationSearch = useState('animation_search', () => null)
const busy = ref(true)
const reassignDialog = ref(null)
const menu = ref(null)
const editing = ref(creating)
const canEdit = computed(
  () =>
    creating ||
    session.is_admin ||
    (item.value.auteurs === session.user?.name && item.value.statut !== 1),
)
const path = `/animations/${route.params.id}`
async function load() {
  error.value = ''
  busy.value = true
  try {
    await catalog.load()
    if (!creating) {
      item.value = await api(path)
      comments.value = (await api(`${path}/comments`)).items
      author.value = item.value.auteurs
      const mediaIds = [
        ...new Set(item.value.sequences.flatMap((seq) => seq.materiel)),
      ]
      await Promise.all(
        mediaIds.map(async (id) => {
          try {
            const media = await api(`/materials/${id}`)
            mediaItems.value[id] = media
          } catch {
            mediaItems.value[id] = { id, nom: 'Média indisponible' }
          }
        }),
      )
    }
    draft.value = structuredClone(toRaw(item.value))
    if (!creating) loadNeighbors()
    // La durée est envoyée par son champ dédié ; le backend l’ajoute aux tags.
    const durationIds = new Set(
      catalog.family('ref.duree').map((tag) => tag.id),
    )
    draft.value.tags = draft.value.tags.filter((id) => !durationIds.has(id))
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
    let result = await fetchNeighbors(animationSearch.value || {})
    // Fiche absente de la dernière recherche : on revient à la liste complète
    if (!result.found && animationSearch.value) {
      animationSearch.value = null
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
    const body = animationPayload(draft.value)
    const durationIds = new Set(
      catalog.family('ref.duree').map((tag) => tag.id),
    )
    body.tags = body.tags.filter((id) => !durationIds.has(id))
    const result = await api(creating ? '/animations' : path, {
      method: creating ? 'POST' : 'PUT',
      body,
    })
    if (creating) {
      editing.value = false
      await navigateTo(`/animations/${result.id}`)
    } else {
      editing.value = false
      await load()
    }
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}
async function action(suffix, method, body) {
  busy.value = true
  error.value = ''
  try {
    await api(path + suffix, { method, body })
    await load()
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}
async function remove() {
  if (
    !window.confirm(
      'Supprimer définitivement cette animation et ses commentaires ?',
    )
  )
    return
  busy.value = true
  error.value = ''
  try {
    await api(path, { method: 'DELETE' })
    await navigateTo('/animations')
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}
function removeSequence(index) {
  if (window.confirm('Retirer cette séquence de l’animation ?'))
    draft.value.sequences.splice(index, 1)
}
async function searchUsers() {
  try {
    suggestions.value = (
      await api('/users', { query: { q: author.value } })
    ).items
  } catch (e) {
    error.value = e.message
  }
}
async function reassign() {
  await action('/author', 'PUT', { auteurs: author.value })
  if (!error.value) reassignDialog.value.close()
}
function openReassign() {
  menu.value.open = false
  reassignDialog.value.showModal()
}
function removeFromMenu() {
  menu.value.open = false
  remove()
}
async function publishComment() {
  await action('/comments', 'POST', { commentaire: comment.value })
  if (!error.value) comment.value = ''
}
function removeComment(id) {
  if (window.confirm('Supprimer ce commentaire ?'))
    action(`/comments/${id}`, 'DELETE')
}
function cancel() {
  draft.value = structuredClone(toRaw(item.value))
  editing.value = false
}
onBeforeRouteLeave(
  () =>
    !editing.value ||
    window.confirm('Quitter sans enregistrer les modifications ?'),
)
let headObserver
const headEl = ref(null)
watch(headEl, (el) => {
  headObserver?.disconnect()
  if (!el || typeof ResizeObserver === 'undefined') return
  headObserver = new ResizeObserver(() => {
    document.documentElement.style.setProperty(
      '--fiche-h',
      `${el.offsetHeight}px`
    )
  })
  headObserver.observe(el)
})
onBeforeUnmount(() => {
  headObserver?.disconnect()
  document.documentElement.style.removeProperty('--fiche-h')
})
onMounted(load)
</script>
<template>
  <NuxtLink to="/animations">← Pédathèque</NuxtLink>
  <p v-if="error" role="alert" class="error">{{ error }}</p>
  <p v-if="busy" role="status">Chargement…</p>
  <template v-if="draft">
    <header ref="headEl" class="fiche-head">
      <div class="fiche-title">
        <template v-if="editing">
          <input
            v-model="draft.titre"
            form="fiche-form"
            class="title-input"
            aria-label="Titre *"
            placeholder="Titre de l’animation *"
            required
            maxlength="100"
          />
        </template>
        <template v-else>
          <h1>{{ item.titre }}</h1>
          <span class="badge" :class="`statut-${item.statut}`">{{
            { 1: 'Validée', 2: 'À valider', 3: 'Brouillon' }[item.statut]
          }}</span>
        </template>
      </div>
      <p v-if="editing" class="muted">
        {{ creating ? 'Création d’une animation' : 'Modification' }} · le titre
        et les références des séquences sont obligatoires.
      </p>
      <p v-else class="muted">
        {{ item.auteurs }} · modifiée le {{ item.date_modif }}
      </p>
      <div v-if="editing" class="actions">
        <PButton
          type="submit"
          form="fiche-form"
          label="Enregistrer"
          :disabled="busy"
        />
        <PButton
          v-if="!creating"
          type="button"
          class="secondary"
          label="Annuler"
          @click="cancel"
        />
        <label class="state-field"
          >État<select v-model="draft.statut" form="fiche-form">
            <option :value="3">Brouillon</option>
            <option :value="2">Complète, à valider</option>
            <option v-if="session.is_admin" :value="1">Validée</option>
          </select></label
        >
      </div>
      <div v-else class="actions">
        <PButton
          v-if="canEdit"
          label="Modifier"
          :disabled="busy"
          @click="editing = true"
        /><PButton
          v-if="session.is_admin && item.statut !== 1"
          label="Valider"
          :disabled="busy"
          @click="action('/validate', 'POST')"
        /><DownloadButton
          :path="`${path}/download`"
          :filename="`${item.titre}.zip`"
          label="Télécharger le kit"
          icon="pi-box"
          show-label
        /><PButton
          class="icon-button"
          aria-label="Imprimer"
          title="Imprimer"
          @click="window.print()"
          ><ActionIcon name="print"
        /></PButton>
        <details v-if="canEdit || session.is_admin" ref="menu" class="more">
          <summary
            class="icon-button"
            aria-label="Autres actions"
            title="Autres actions"
          >
            <ActionIcon name="more" />
          </summary>
          <ul>
            <li v-if="session.is_admin">
              <button type="button" :disabled="busy" @click="openReassign">
                Réattribuer la fiche…
              </button>
            </li>
            <li v-if="canEdit">
              <button
                type="button"
                class="danger-item"
                :disabled="busy"
                @click="removeFromMenu"
              >
                Supprimer l’animation
              </button>
            </li>
          </ul>
        </details>
      </div>
    </header>
      <nav v-if="neighbors && !editing" class="fiche-nav" aria-label="Animations voisines">
        <NuxtLink
          v-if="neighbors.previous"
          class="nav-arrow nav-prev"
          :to="`/animations/${neighbors.previous.id}`"
          :aria-label="`Animation précédente : ${neighbors.previous.titre}`"
          :title="`Précédente : ${neighbors.previous.titre}`"
          >‹</NuxtLink
        >
        <NuxtLink
          v-if="neighbors.next"
          class="nav-arrow nav-next"
          :to="`/animations/${neighbors.next.id}`"
          :aria-label="`Animation suivante : ${neighbors.next.titre}`"
          :title="`Suivante : ${neighbors.next.titre}`"
          >›</NuxtLink
        >
      </nav>
      <form
        v-if="editing"
        id="fiche-form"
        class="fiche-layout"
        @submit.prevent="save"
      >
        <aside class="fiche-aside edit-aside">
          <section class="summary card edit-summary">
            <RefSelect
              v-model="draft.fk_duree_id"
              :items="catalog.family('ref.duree')"
              label="Durée totale"
            />
            <label>Lieu<input v-model="draft.lieu" /></label>
            <TagPicker
              v-for="group in [
                'ref.thematiques',
                'ref.lieux',
                'ref.saison',
                'ref.public',
              ]"
              :key="group"
              v-model="draft.tags"
              :items="catalog.family(group)"
              :legend="
                catalog.items.value.find((tag) => tag.code === group)?.label ||
                group
              "
            />
          </section>
          <div class="aside-spacer" aria-hidden="true"></div>
        </aside>
        <div class="fiche-main">
          <fieldset
            v-for="[key, label] in animationFields"
            :key="key"
            class="block"
            :class="`block-${key}`"
          >
            <legend>{{ label }}</legend>
            <RichEditor v-model="draft[key]" :label="label" />
          </fieldset>
          <h2>Les séquences</h2>
          <ol class="timeline">
            <li
              v-for="(seq, index) in draft.sequences"
              :key="seq.id || index"
              class="sequence"
              :class="catalog.sequenceKind(seq)"
            >
              <span class="step" aria-hidden="true">{{ index + 1 }}</span>
              <article class="card">
                <header class="seq-edit-head">
                  <input
                    v-model="seq.titre"
                    class="seq-title-input"
                    aria-label="Titre de la séquence *"
                    :title="`Séquence ${index + 1}`"
                    placeholder="Titre de la séquence *"
                    required
                    maxlength="100"
                  />
                  <div class="seq-tools">
                    <PButton
                      type="button"
                      class="icon-button secondary"
                      aria-label="Monter la séquence"
                      title="Monter"
                      :disabled="index === 0"
                      @click="moveSequence(draft.sequences, index, -1)"
                      ><ActionIcon name="up"
                    /></PButton>
                    <PButton
                      type="button"
                      class="icon-button secondary"
                      aria-label="Descendre la séquence"
                      title="Descendre"
                      :disabled="index === draft.sequences.length - 1"
                      @click="moveSequence(draft.sequences, index, 1)"
                      ><ActionIcon name="down"
                    /></PButton>
                    <PButton
                      type="button"
                      class="icon-button secondary danger-icon"
                      aria-label="Retirer la séquence"
                      title="Retirer la séquence"
                      @click="removeSequence(index)"
                      ><ActionIcon name="delete"
                    /></PButton>
                  </div>
                </header>
                <div class="grid seq-refs">
                  <RefSelect
                    v-for="[key, family, label] in sequenceRefs"
                    :key="key"
                    v-model="seq[key]"
                    :items="catalog.family(family)"
                    :label="label + ' *'"
                    required
                  />
                  <div>
                    <label :for="`seq-duree-${index}`">Durée (minutes) *</label>
                    <DurationStepper
                      :id="`seq-duree-${index}`"
                      v-model="seq.duree_minutes"
                      :min="1"
                      :step-floor="5"
                      :max="1440"
                      required
                    />
                  </div>
                </div>
                <fieldset
                  v-for="[key, label] in sequenceFields"
                  :key="key"
                  class="block block-sequence"
                  :class="`block-seq-${key}`"
                >
                  <legend>{{ label }}</legend>
                  <RichEditor v-model="seq[key]" :label="label" />
                </fieldset>
                <MediaEditor v-model="seq.materiel" :media="mediaItems" />
              </article>
            </li>
          </ol>
          <PButton
            type="button"
            class="secondary"
            label="Ajouter une séquence"
            @click="draft.sequences.push(newSequence())"
          />
        </div>
      </form>
      <div v-else class="fiche-layout">
        <aside class="fiche-aside">
          <AnimationSummary :item="item" />
          <SequenceToc :sequences="item.sequences" />
        </aside>
        <div class="fiche-main">
          <fieldset
            v-for="[key, label] in animationFields"
            v-show="item[key]"
            :key="key"
            class="block"
            :class="`block-${key}`"
          >
            <legend>{{ label }}</legend>
            <RichText :text="item[key]" />
          </fieldset>
          <h2>Les séquences</h2>
          <ol class="timeline">
            <li
              v-for="(seq, index) in item.sequences"
              :id="`seq-${index + 1}`"
              :key="seq.id"
              class="sequence"
              :class="catalog.sequenceKind(seq)"
            >
              <span class="step" aria-hidden="true">{{ index + 1 }}</span>
              <article class="card">
                <header>
                  <h3>{{ seq.titre }}</h3>
                  <ul class="chips" aria-label="Caractéristiques">
                    <li
                      v-for="[key, , label] in sequenceRefs"
                      v-show="seq[key]"
                      :key="key"
                      :title="label"
                    >
                      {{ catalog.label(seq[key]) }}
                    </li>
                    <li
                      v-show="formatMinutes(seq.duree_minutes)"
                      class="chip-duration"
                      title="Durée"
                    >
                      {{ formatMinutes(seq.duree_minutes) }}
                    </li>
                  </ul>
                </header>
                <fieldset
                  v-show="seq.description"
                  class="block block-sequence block-deroulement"
                >
                  <legend>Déroulement</legend>
                  <RichText :text="seq.description" />
                </fieldset>
                <fieldset
                  v-show="seq.objectifs"
                  class="block block-sequence block-objectifs"
                >
                  <legend>Objectifs</legend>
                  <RichText :text="seq.objectifs" />
                </fieldset>
                <fieldset
                  v-show="seq.materiel_div"
                  class="block block-sequence block-materiel"
                >
                  <legend>Matériel complémentaire</legend>
                  <RichText :text="seq.materiel_div" />
                </fieldset>
                <div v-if="seq.materiel.length">
                  <h4>Médias</h4>
                  <SequenceMedia
                    :items="seq.materiel.map((id) => mediaItems[id])"
                  />
                </div>
              </article>
            </li>
          </ol>
          <details class="comments card">
            <summary>
              <h2>Commentaires ({{ comments.length }})</h2>
            </summary>
            <article v-for="entry in comments" :key="entry.id" class="comment">
              <header>
                <strong>{{ entry.auteur }}</strong>
                <span class="muted">{{ entry.date }}</span>
                <PButton
                  v-if="session.is_admin || entry.auteur === session.user.name"
                  class="icon-button comment-delete"
                  aria-label="Supprimer le commentaire"
                  title="Supprimer le commentaire"
                  :disabled="busy"
                  @click="removeComment(entry.id)"
                  ><ActionIcon name="delete"
                /></PButton>
              </header>
              <p class="prose">{{ entry.commentaire }}</p>
            </article>
            <p v-if="!comments.length" class="muted">Aucun commentaire.</p>
            <form @submit.prevent="publishComment">
              <label
                >Votre commentaire<textarea
                  v-model="comment"
                  required
                  maxlength="100000"
                /></label
              ><PButton type="submit" label="Publier" :disabled="busy" />
            </form>
          </details>
        </div>
      </div>
    <dialog v-if="session.is_admin" ref="reassignDialog" class="reassign">
      <form @submit.prevent="reassign">
        <h2>Réattribuer la fiche</h2>
        <label
          >Auteur<input
            v-model="author"
            list="users"
            required
            maxlength="200"
            @input="author.trim().length >= 2 && searchUsers()"
        /></label>
        <datalist id="users">
          <option v-for="name in suggestions" :key="name" :value="name" />
        </datalist>
        <div class="actions">
          <PButton type="submit" label="Réattribuer" :disabled="busy" />
          <PButton
            type="button"
            class="secondary"
            label="Annuler"
            @click="reassignDialog.close()"
          />
        </div>
      </form>
    </dialog>
  </template>
</template>
<style scoped>
.fiche-head {
  margin: 12px 0 20px;
}
.fiche-head {
  position: sticky;
  top: var(--site-h, 0px);
  z-index: 15;
  margin: 0 0 20px;
  padding: 12px 0 8px;
  border-bottom: 1px solid var(--c-line);
  background: var(--c-bg);
}
.fiche-main header {
  position: static;
  z-index: auto;
}
.fiche-title {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
}
.fiche-title h1 {
  margin: 0;
}
.fiche-head p {
  margin: 4px 0 12px;
}
.fiche-layout {
  display: grid;
  grid-template-columns: 420px minmax(0, 1fr);
  gap: 24px;
  align-items: start;
}
.fiche-main {
  grid-column: 2;
  grid-row: 1;
  min-width: 0;
}
.fiche-aside {
  grid-column: 1;
  grid-row: 1;
  position: sticky;
  top: calc(var(--site-h, 0px) + var(--fiche-h, 0px) + 16px);
  display: grid;
  gap: 16px;
}
.fiche-aside .card {
  margin: 0;
}
.timeline {
  position: relative;
  margin: 0;
  padding: 0;
  list-style: none;
}
.timeline {
  --seq-color: var(--c-primary);
}
.sequence::before {
  content: '';
  position: absolute;
  top: 0;
  bottom: -16px;
  left: 17px;
  width: 2px;
  background: color-mix(in srgb, var(--seq-color) 40%, white);
}
.sequence:first-child::before {
  top: 16px;
}
.sequence:last-child::before {
  bottom: 16px;
}
.sequence {
  position: relative;
  padding-left: 52px;
  scroll-margin-top: max(120px, 30vh);
}
.step {
  position: absolute;
  top: 12px;
  left: 0;
  display: grid;
  place-items: center;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: var(--seq-color);
  color: #fff;
  font-weight: 700;
  box-shadow: 0 0 0 4px var(--c-bg);
}
.sequence > .card {
  border-color: color-mix(in srgb, var(--seq-color) 35%, var(--c-line));
}
.sequence h3 {
  margin: 0 0 8px;
}
.sequence h4 {
  margin: 14px 0 4px;
  font-size: 0.8rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--c-muted);
}
.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.chips li {
  padding: 2px 10px;
  border-radius: 20px;
  background: var(--c-primary-soft);
  color: var(--c-primary-dark);
  font-size: 0.85rem;
}
.chips .chip-duration {
  background: var(--c-primary-mid);
  font-weight: 600;
}
@media (max-width: 600px) {
  .sequence {
    padding-left: 44px;
  }
  .step {
    width: 30px;
    height: 30px;
  }
  .sequence::before {
    left: 14px;
  }
}
.block {
  --accent: var(--c-primary);
  min-width: 0;
  margin: 0 0 18px;
  padding: 8px 20px 14px 22px;
  border: 1.5px solid color-mix(in srgb, var(--accent) 45%, white);
  border-radius: var(--radius);
  background: color-mix(in srgb, var(--accent) 7%, white);
}
.block legend {
  padding: 0 10px;
  font-size: 0.98rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: color-mix(in srgb, var(--accent) 75%, black);
}
.block-sequence {
  margin: 14px 0 0;
  padding: 4px 16px 10px 18px;
}
.block-deroulement {
  background: var(--c-surface);
}
.block-materiel {
  --accent: #b07a1a;
}
.block .prose {
  margin: 0;
}
.block-objectifs {
  --accent: #1f8a70;
}
.block-pre_anim {
  --accent: #3a6fc4;
}
.block-post_anim {
  --accent: #8a4fc0;
}
.block-public_specifique {
  --accent: #7a7167;
}
.block-seq-description {
  background: var(--c-surface);
}
.block-seq-objectifs {
  --accent: #1f8a70;
}
.block-seq-materiel_div {
  --accent: #b07a1a;
}
.block .rich {
  margin-top: 0;
  border-color: color-mix(in srgb, var(--accent) 30%, white);
}
.title-input {
  flex: 1;
  min-width: min(100%, 320px);
  margin: 0;
  font-size: 1.5rem;
  font-weight: 500;
}
.state-field {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
}
.state-field select {
  width: auto;
  margin: 0;
}
.edit-aside {
  max-height: calc(
    100vh - var(--site-h, 0px) - var(--fiche-h, 0px) - 32px
  );
  overflow-y: auto;
  overscroll-behavior: contain;
}
.aside-spacer {
  height: 50px;
}
.edit-summary {
  gap: 4px;
}
.edit-summary label,
.edit-summary :deep(label) {
  margin: 8px 0 0;
}
.edit-summary fieldset {
  margin: 8px 0 0;
  padding: 10px 12px;
  background: var(--c-soft);
}
.edit-summary legend {
  font-size: 0.8rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--c-muted);
}
.seq-edit-head {
  display: flex;
  align-items: center;
  gap: 8px;
}
.seq-title-input {
  flex: 1;
  margin: 0;
  font-size: 1.17rem;
  font-weight: 600;
}
.seq-tools {
  display: flex;
  gap: 4px;
}
.seq-tools :deep(.icon-button) {
  min-width: 36px;
  min-height: 36px;
  margin: 0;
  padding: 6px;
}
.seq-tools :deep(.danger-icon) {
  color: var(--c-danger);
}
.seq-refs {
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 0 12px;
  margin-top: 4px;
}
.sequence :deep(details) {
  margin-top: 14px;
}
@media (max-width: 900px) {
  .fiche-layout {
    grid-template-columns: minmax(0, 1fr);
  }
  .fiche-main,
  .fiche-aside {
    grid-column: 1;
    grid-row: auto;
    position: static;
  }
  .edit-aside {
    max-height: none;
    overflow: visible;
  }
  .aside-spacer {
    display: none;
  }
}
@media print {
  .fiche-layout {
    display: block;
  }
}
.statut-1 {
  background: #e3f4e4;
  color: #1e6b2a;
}
.fiche-head :deep(.icon-button) {
  min-width: 40px;
  min-height: 40px;
  padding: 8px;
  background: var(--c-primary-soft);
  color: var(--c-primary-dark);
}
.fiche-head :deep(.icon-button.danger) {
  background: var(--c-primary-soft);
  color: var(--c-danger);
}
.fiche-head .actions {
  align-items: center;
  gap: 8px;
}
.more {
  position: relative;
}
.more summary {
  display: grid;
  place-items: center;
  list-style: none;
  cursor: pointer;
  border-radius: var(--radius);
}
.more summary::-webkit-details-marker {
  display: none;
}
.more ul {
  position: absolute;
  right: 0;
  z-index: 10;
  min-width: 220px;
  margin: 4px 0 0;
  padding: 4px;
  list-style: none;
  background: var(--c-surface);
  border: 1px solid var(--c-line);
  border-radius: var(--radius);
  box-shadow: var(--shadow-hover);
}
.more li button {
  width: 100%;
  padding: 8px 12px;
  border: 0;
  background: transparent;
  color: var(--c-text);
  font: inherit;
  text-align: left;
  cursor: pointer;
  border-radius: var(--radius);
}
.more li button:hover:not(:disabled) {
  background: var(--c-primary-soft);
}
.more .danger-item {
  color: var(--c-danger);
}
.reassign {
  width: min(440px, 92vw);
  padding: 24px;
  border: 1px solid var(--c-line);
  border-radius: var(--radius);
}
.reassign h2 {
  margin-top: 0;
}
.reassign .actions {
  margin-top: 16px;
}
.comments > summary {
  cursor: pointer;
  list-style: none;
}
.comments > summary::-webkit-details-marker {
  display: none;
}
.comments > summary h2 {
  display: inline;
  margin: 0;
  font-size: 1.1rem;
}
.comments > summary::before {
  content: '▸ ';
}
.comments[open] > summary::before {
  content: '▾ ';
}
.comment {
  padding: 12px 0;
  border-bottom: 1px solid var(--c-line);
}
.comment header {
  display: flex;
  align-items: center;
  gap: 10px;
}
.comment .prose {
  margin: 6px 0 0;
}
.comment-delete {
  margin-left: auto;
  min-width: 32px;
  min-height: 32px;
  padding: 4px;
  background: transparent;
  color: var(--c-danger);
}
@media print {
  .fiche-nav {
    display: none;
  }
  .fiche-aside {
    position: static;
  }
  .fiche-aside .toc,
  .comments,
  .more,
  .reassign {
    display: none;
  }
  .sequence {
    break-inside: avoid;
  }
}
.nav-arrow {
  position: fixed;
  top: 50%;
  z-index: 20;
  display: grid;
  place-items: center;
  width: 48px;
  height: 76px;
  transform: translateY(-50%);
  border-radius: var(--radius);
  background: var(--c-primary-mid);
  color: var(--c-primary-dark);
  font-size: 2.4rem;
  line-height: 1;
  text-decoration: none;
  box-shadow: 0 2px 8px rgb(180 100 0 / 20%);
  opacity: 0.85;
  transition: opacity 0.15s;
}
.nav-arrow:hover,
.nav-arrow:focus-visible {
  background: var(--c-primary);
  color: var(--c-on-primary);
  opacity: 1;
}
.nav-prev {
  left: 6px;
}
.nav-next {
  right: 6px;
}
@media (max-width: 900px) {
  .nav-arrow {
    width: 30px;
    height: 48px;
  }
}
</style>
