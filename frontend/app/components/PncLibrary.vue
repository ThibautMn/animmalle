<script setup>
// Bibliothèque du PNC : recherche d'un taxon Taxref (autocomplétion), puis médias TaxHub de ce taxon.
const emit = defineEmits(['add'])
const api = useApi()
const catalog = useCatalog()
const query = ref('')
const suggestions = ref([])
const listOpen = ref(false)
const taxon = ref(null)
const medias = ref([])
const loaded = ref(false)
const busy = ref(false)
const importing = ref(0)
const error = ref('')
const previewed = ref(null)
const previewDialog = ref(null)
let timer = null
let searchId = 0
const MIN_CHARS = 3
const EXTENSIONS = {
  image: ['jpg', 'jpeg', 'png', 'gif', 'webp'],
  video: ['mp4', 'm4v', 'mov', 'avi', 'wmv', 'webm'],
  audio: ['mp3', 'wma', 'wav', 'ogg', 'm4a'],
  pdf: ['pdf']
}
function extension(media) {
  return (new URL(media.url).pathname.split('.').pop() || '').toLowerCase()
}
function kind(media) {
  return Object.keys(EXTENSIONS).find((name) => EXTENSIONS[name].includes(extension(media))) || 'file'
}
// Type de média Anim'Malle le plus proche du format ; premier type par défaut.
function typeFor(media) {
  const types = catalog.family('ref.type_mat')
  const patterns = { image: /image|photo/i, video: /vid[ée]o|film/i, audio: /son|audio|musique/i, pdf: /pdf|document|texte/i }
  const found = types.find((type) => patterns[kind(media)]?.test(type.label))
  return (found || types[0])?.id
}
function taxonLabel(item) {
  return item.nom_vern ? `${item.nom_vern.split(',')[0]} (${item.lb_nom})` : item.lb_nom
}
function suggest(event) {
  clearTimeout(timer)
  // Valeur lue sur le champ : ne dépend pas de l'ordre des écouteurs de v-model.
  const term = event.target.value.trim()
  if (term.length < MIN_CHARS) {
    suggestions.value = []
    listOpen.value = false
    return
  }
  timer = setTimeout(async () => {
    const current = ++searchId
    try {
      const result = await api('/taxhub/taxa', { query: { q: term } })
      if (current !== searchId) return
      suggestions.value = result.items
      listOpen.value = true
      error.value = ''
    } catch (e) {
      if (current === searchId) error.value = e.message
    }
  }, 300)
}
async function choose(item) {
  listOpen.value = false
  suggestions.value = []
  query.value = taxonLabel(item)
  taxon.value = null
  medias.value = []
  loaded.value = false
  busy.value = true
  error.value = ''
  try {
    const [detail, list] = await Promise.all([
      api(`/taxhub/taxa/${item.cd_ref}`),
      api(`/taxhub/taxa/${item.cd_ref}/media`)
    ])
    taxon.value = detail
    medias.value = list.items
    loaded.value = true
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}
function preview(media) {
  previewed.value = media
  previewDialog.value.showModal()
}
async function pick(media) {
  if (importing.value) return
  importing.value = media.id_media
  error.value = ''
  try {
    const created = await api('/taxhub/import', {
      method: 'POST',
      body: { cd_ref: taxon.value.cd_ref, id_media: media.id_media, fk_type_mat_id: typeFor(media) }
    })
    emit('add', created)
  } catch (e) {
    error.value = e.message
  } finally {
    importing.value = 0
  }
}
onBeforeUnmount(() => clearTimeout(timer))
</script>
<template>
  <div class="pnc-library">
    <div class="pnc-search">
      <input
        v-model="query"
        type="search"
        role="combobox"
        autocomplete="off"
        placeholder="Rechercher une espèce (nom commun ou scientifique)…"
        aria-label="Rechercher un taxon dans Taxref"
        aria-autocomplete="list"
        aria-controls="pnc-suggestions"
        :aria-expanded="listOpen"
        @input="suggest"
        @keydown.escape="listOpen = false"
      />
      <ul v-if="listOpen" id="pnc-suggestions" role="listbox" class="pnc-suggestions">
        <li v-if="!suggestions.length" class="pnc-empty">Aucun taxon trouvé.</li>
        <li v-for="item in suggestions" :key="item.cd_ref" role="option">
          <button type="button" @click="choose(item)">
            <strong>{{ item.nom_vern ? item.nom_vern.split(',')[0] : item.lb_nom }}</strong>
            <em v-if="item.nom_vern"> {{ item.lb_nom }}</em>
            <small v-if="item.group2_inpn"> — {{ item.group2_inpn }}</small>
          </button>
        </li>
      </ul>
    </div>
    <p v-if="error" role="alert" class="error">{{ error }}</p>
    <p v-if="busy" role="status">Chargement des médias…</p>
    <p v-if="taxon" class="pnc-taxon">
      <strong>{{ taxon.nom_vern ? taxon.nom_vern.split(',')[0] : taxon.lb_nom }}</strong>
      <em> {{ taxon.nom_valide || taxon.lb_nom }}</em> (cd_ref {{ taxon.cd_ref }})
    </p>
    <p v-if="loaded && !medias.length">Aucun média pour ce taxon.</p>
    <div v-if="medias.length" class="sequence-images">
      <figure v-for="media in medias" :key="media.id_media">
        <span class="selectable-thumb">
          <span class="thumbnail-preview">
            <button type="button" :aria-label="`Aperçu de ${media.titre}`" @click="preview(media)">
              <span v-if="kind(media) === 'image'" class="video-thumbnail thumbnail-image">
                <img :src="media.url" :alt="media.titre" loading="lazy" referrerpolicy="no-referrer" />
              </span>
              <span v-else :class="['file-tile', `file-tile--${kind(media)}`]">
                <FileTypeIcon :kind="kind(media)" />
                <span class="file-ext">{{ extension(media).toUpperCase() }}</span>
              </span>
            </button>
          </span>
          <button
            type="button"
            class="add-media-button"
            data-tooltip="Ajouter le média"
            :aria-label="`Ajouter le média ${media.titre}`"
            :disabled="Boolean(importing)"
            @click="pick(media)"
          >
            <ActionIcon name="add" />
          </button>
        </span>
        <figcaption>
          {{ media.titre || 'Sans titre' }}
        </figcaption>
      </figure>
    </div>
    <dialog
      ref="previewDialog"
      class="preview-dialog"
      aria-label="Aperçu du média"
      @close="previewed = null"
      @click="$event.target === previewDialog && previewDialog.close()"
    >
      <div class="toolbar">
        <h2>{{ previewed?.titre || 'Aperçu du média' }}</h2>
        <PButton type="button" label="Fermer" @click="previewDialog.close()" />
      </div>
      <div v-if="previewed" class="media-preview">
        <img v-if="kind(previewed) === 'image'" :src="previewed.url" :alt="previewed.titre" referrerpolicy="no-referrer" />
        <video v-else-if="kind(previewed) === 'video'" :src="previewed.url" controls />
        <audio v-else-if="kind(previewed) === 'audio'" :src="previewed.url" controls />
        <iframe v-else-if="kind(previewed) === 'pdf'" :src="previewed.url" title="Aperçu du document PDF" />
        <p v-else>Aperçu indisponible pour ce format.</p>
        <p v-if="previewed.auteur || previewed.source || previewed.licence" class="pnc-credit">
          {{ [previewed.auteur, previewed.source, previewed.licence].filter(Boolean).join(' - ') }}
        </p>
      </div>
    </dialog>
  </div>
</template>
