<script setup>
import { highlightParts, pageEntries, splitTerms } from '../../lib/search.mjs'
const api = useApi()
const catalog = useCatalog()
const route = useRoute()
const tabs = [
  { key: 'animations', label: 'Animations' },
  { key: 'outils', label: 'Outils facilitateurs' },
  { key: 'media', label: 'Média' }
]
const page_size = 20
const kind = computed(() =>
  tabs.some((tab) => tab.key === route.query.onglet) ? route.query.onglet : 'animations'
)
const query_text = computed(() =>
  typeof route.query.q === 'string' ? route.query.q.trim() : ''
)
const terms = computed(() => splitTerms(query_text.value))
// Filtres propres à chaque onglet (cases à cocher), conservés quand on change d'onglet.
const filters = reactive({
  animations: { statut: [], non_statut: [], tag: [], non_tag: [] },
  outils: { type: [], non_type: [], difficulte: [], non_difficulte: [] },
  media: { type: [], non_type: [], tag: [], non_tag: [] }
})
const items = ref([])
const total = ref(0)
const counts = ref(null)
const page = ref(1)
const busy = ref(false)
const error = ref('')
let requestId = 0
async function search(reset = false) {
  if (reset) page.value = 1
  const current = ++requestId
  error.value = ''
  if (!terms.value.length) {
    items.value = []
    total.value = 0
    counts.value = null
    busy.value = false
    return
  }
  busy.value = true
  try {
    const result = await api('/search', {
      query: {
        q: query_text.value,
        kind: kind.value,
        page: page.value,
        page_size,
        ...filters[kind.value]
      }
    })
    if (current !== requestId) return
    items.value = result.items
    total.value = result.total
    counts.value = result.counts
  } catch (e) {
    if (current !== requestId) return
    items.value = []
    total.value = 0
    error.value = e.message
  } finally {
    if (current === requestId) busy.value = false
  }
}
let timer
watch(
  filters,
  () => {
    clearTimeout(timer)
    timer = setTimeout(() => search(true), 300)
  },
  { deep: true }
)
watch(
  () => [route.query.q, route.query.onglet],
  () => search(true)
)
onBeforeUnmount(() => clearTimeout(timer))
onMounted(async () => {
  search(true)
  try {
    await catalog.load()
  } catch (e) {
    error.value = e.message
  }
})
const page_count = computed(() => Math.max(1, Math.ceil(total.value / page_size)))
const entries = computed(() => pageEntries(page.value, page_count.value))
async function go(target) {
  if (target < 1 || target > page_count.value || target === page.value) return
  page.value = target
  await search()
  window.scrollTo({ top: 0, behavior: 'smooth' })
}
// Critères de la recherche de médias, pour les flèches de l'aperçu.
const media_query = computed(() => ({ q: terms.value, ...filters.media }))
const parts = (text) => highlightParts(text, terms.value)
const statuses = [
  [1, 'Validée'],
  [2, 'À valider'],
  [3, 'Brouillon']
]
const statusLabels = Object.fromEntries(statuses.map(([value, label]) => [String(value), label]))
const summaryOf = (prefix = '') =>
  ['statut', 'tag', 'type', 'difficulte']
    .flatMap((key) =>
      (filters[kind.value][prefix + key] || []).map((id) =>
        key === 'statut' ? statusLabels[id] : catalog.label(id)
      )
    )
    .filter(Boolean)
const summary_included = computed(() => summaryOf())
const summary_excluded = computed(() => summaryOf('non_'))
const animationGroups = ['ref.thematiques', 'ref.lieux', 'ref.saison', 'ref.public', 'ref.duree']
const legend = (group) =>
  catalog.items.value.find((item) => item.code === group)?.label || group.replace('ref.', '')
const link = (item) =>
  kind.value === 'animations'
    ? `/animations/${item.id}`
    : `/materials/${item.id}${kind.value === 'outils' ? '?kind=outil' : ''}`
</script>
<template>
  <div class="toolbar">
    <h1>Résultats de la recherche</h1>
  </div>
  <p v-if="!terms.length" class="muted">
    Saisissez un ou plusieurs mots dans la barre de recherche : tous doivent figurer dans le
    contenu, sans ordre imposé.
  </p>
  <template v-else>
    <p class="muted search-summary">
      Mots recherchés (tous requis) :
      <mark v-for="term in terms" :key="term" class="search-term">{{ term }}</mark>
    </p>
    <div class="search-tabs" role="tablist" aria-label="Type de résultats">
      <NuxtLink
        v-for="tab in tabs"
        :key="tab.key"
        role="tab"
        :aria-selected="kind === tab.key"
        :class="['search-tab', { active: kind === tab.key }]"
        :to="{ path: '/search', query: { q: query_text, onglet: tab.key } }"
        replace
      >
        {{ tab.label }}
        <span v-if="counts" class="badge">{{ counts[tab.key] }}</span>
      </NuxtLink>
    </div>
    <div :class="['catalog-layout with-sidebar', kind === 'outils' && 'tools-tint']">
      <form class="card filters" aria-label="Filtres" @submit.prevent="search(true)">
        <template v-if="kind === 'animations'">
          <fieldset class="status-box">
            <legend>Statut</legend>
            <label v-for="[value, label] in statuses" :key="value" class="check"
              ><TriCheck
                v-model="filters.animations.statut"
                v-model:excluded="filters.animations.non_statut"
                :value="String(value)"
              />{{
                label
              }}</label
            >
          </fieldset>
          <TagPicker
            v-for="group in animationGroups"
            :key="group"
            v-model="filters.animations.tag"
            v-model:excluded="filters.animations.non_tag"
            :items="catalog.family(group)"
            :legend="legend(group)"
          />
        </template>
        <template v-else-if="kind === 'outils'">
          <TagPicker
            v-model="filters.outils.type"
            v-model:excluded="filters.outils.non_type"
            :items="catalog.family('ref.type_outil')"
            legend="Type d'outil"
          />
          <TagPicker
            v-model="filters.outils.difficulte"
            v-model:excluded="filters.outils.non_difficulte"
            :items="catalog.family('ref.difficulte')"
            legend="Difficulté"
          />
        </template>
        <template v-else>
          <TagPicker
            v-model="filters.media.type"
            v-model:excluded="filters.media.non_type"
            :items="catalog.family('ref.type_mat')"
            legend="Types de ressources"
          />
          <TagPicker
            v-model="filters.media.tag"
            v-model:excluded="filters.media.non_tag"
            :items="catalog.family('ref.thematiques')"
            legend="Thématiques"
          />
        </template>
      </form>
      <div class="catalog-results" role="tabpanel">
        <p v-if="error" role="alert" class="error">{{ error }}</p>
        <div v-if="busy" class="loading-overlay">
          <p role="status" class="loading-status">
            <span class="loader-bar" aria-hidden="true" />Recherche en cours…
          </p>
        </div>
        <div class="results-content" :inert="busy" :aria-busy="busy">
          <FilterSummary :included="summary_included" :excluded="summary_excluded" />
          <p v-if="!busy && !error" class="muted" aria-live="polite">
            {{ total }} résultat{{ total > 1 ? 's' : '' }}
          </p>
          <PaginationNav
            :page="page"
            :page-count="page_count"
            :entries="entries"
            :busy="busy"
            @go="go"
          />
          <SequenceMedia
            v-if="kind === 'media'"
            :items="items"
            :query="media_query"
            details
            @deleted="
              (id) => {
                items = items.filter((entry) => entry.id !== id)
                search()
              }
            "
            @updated="
              (updated) =>
                (items = items.map((entry) =>
                  entry.id === updated.id ? { ...entry, ...updated } : entry
                ))
            "
          />
          <div v-else class="resource-list cards-list search-results">
            <article v-for="item in items" :key="item.id" class="card">
              <div class="card-title-row">
                <h2>
                  <NuxtLink :to="link(item)"
                    ><template v-for="(part, index) in parts(item.titre || item.nom)" :key="index"
                      ><mark v-if="part.hit">{{ part.text }}</mark
                      ><template v-else>{{ part.text }}</template></template
                    ></NuxtLink
                  >
                </h2>
                <span class="duration-badges">
                  <span
                    v-if="kind === 'animations'"
                    class="badge"
                    :class="`statut-${item.statut}`"
                    >{{
                    Object.fromEntries(statuses)[item.statut]
                  }}</span>
                  <span
                    v-if="catalog.label(item.fk_type_outil_id || item.fk_type_mat_id)"
                    class="badge duration-badge"
                    >{{ catalog.label(item.fk_type_outil_id || item.fk_type_mat_id) }}</span
                  >
                  <span v-if="item.extension" class="badge duration-badge">{{
                    item.extension
                  }}</span>
                </span>
              </div>
              <p v-if="kind === 'animations'" class="pictos">
                <PictoIcon v-for="tag in item.tags" :id="tag" :key="tag" />
              </p>
              <p v-if="item.debut" class="search-start">
                <template v-for="(part, index) in parts(item.debut)" :key="index"
                  ><mark v-if="part.hit">{{ part.text }}</mark
                  ><template v-else>{{ part.text }}</template></template
                >
              </p>
              <ul v-if="item.extraits?.length" class="search-snippets">
                <li v-for="(extract, index) in item.extraits" :key="index">
                  <span class="snippet-source">{{ extract.source }}</span>
                  <span class="snippet-text"
                    ><template v-for="(part, n) in parts(extract.text)" :key="n"
                      ><mark v-if="part.hit">{{ part.text }}</mark
                      ><template v-else>{{ part.text }}</template></template
                    ></span
                  >
                </li>
              </ul>
              <p v-if="kind === 'animations'" class="muted">{{ item.auteurs }}</p>
            </article>
          </div>
          <p v-if="!busy && !error && !items.length">Aucun résultat pour ces critères.</p>
          <PaginationNav
            :page="page"
            :page-count="page_count"
            :entries="entries"
            :busy="busy"
            @go="go"
          />
        </div>
      </div>
    </div>
  </template>
</template>
