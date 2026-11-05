<script setup>
import { useSessionStore } from '~/stores/session'
const props = defineProps({ kind: { type: String, default: 'animation' } })
const session = useSessionStore()
const api = useApi()
const catalog = useCatalog()
const route = useRoute()
const animations = props.kind === 'animation'
const endpoint = animations ? '/animations' : '/materials'
const heading = animations
  ? 'La pédathèque'
  : props.kind === 'outil'
    ? 'Les outils facilitateurs'
    : 'La médiathèque'
const items = ref([])
const tags = ref([])
const types = ref([])
const author = ref(route.query.auteur || '')
const authors = ref([])
const status = ref('')
const page = ref(1)
const total = ref(0)
const busy = ref(false)
const error = ref('')
let requestId = 0
async function search(reset = false) {
  if (reset) page.value = 1
  const current = ++requestId
  busy.value = true
  error.value = ''
  try {
    const query = { page: page.value, page_size: 20, tag: tags.value }
    if (animations) {
      if (author.value) query.auteur = author.value
      if (status.value) query.statut = status.value
    } else {
      query.kind = props.kind
      query.type = types.value
    }
    const result = await api(endpoint, { query })
    if (current === requestId) {
      items.value = result.items
      total.value = result.total
    }
  } catch (e) {
    if (current === requestId) error.value = e.message
  } finally {
    if (current === requestId) busy.value = false
  }
}
async function turn(delta) {
  page.value += delta
  await search()
}
onMounted(async () => {
  await search()
  try {
    await catalog.load()
    if (animations) authors.value = (await api('/authors')).items
  } catch (e) {
    error.value = e.message
  }
})
</script>
<template>
  <div class="toolbar">
    <h1>{{ heading }}</h1>
    <NuxtLink
      class="button"
      :to="`${endpoint}/nouveau${animations ? '' : '?kind=' + kind}`"
      >{{
        animations ? 'Créer une animation' : 'Importer une ressource'
      }}</NuxtLink
    >
  </div>
  <form class="card" @submit.prevent="search(true)">
    <div v-if="animations" class="grid">
      <label
        >Auteur<input v-model="author" list="authors" /><datalist id="authors">
          <option
            v-for="name in authors"
            :key="name"
            :value="name"
          /></datalist></label
      ><label
        >Statut<select v-model="status">
          <option value="">Tous</option>
          <option value="1">Validée</option>
          <option value="2">À valider</option>
          <option value="3">Brouillon</option>
        </select></label
      >
    </div>
    <PButton
      v-if="animations"
      type="button"
      class="secondary"
      label="Mes animations"
      @click="
        () => {
          author = session.user.name
          search(true)
        }
      "
    />
    <TagPicker
      v-if="!animations"
      v-model="types"
      :items="
        catalog.family(kind === 'outil' ? 'ref.type_outil' : 'ref.type_mat')
      "
      legend="Types de ressources"
    />
    <TagPicker
      v-for="group in animations
        ? [
            'ref.thematiques',
            'ref.lieux',
            'ref.saison',
            'ref.public',
            'ref.duree'
          ]
        : ['ref.thematiques']"
      :key="group"
      v-model="tags"
      :items="catalog.family(group)"
      :legend="
        catalog.items.value.find((item) => item.code === group)?.label ||
        group.replace('ref.', '')
      "
    />
    <PButton type="submit" label="Rechercher" :disabled="busy" />
  </form>
  <p v-if="error" role="alert" class="error">{{ error }}</p>
  <p v-if="busy" role="status">Recherche en cours…</p>
  <p v-else aria-live="polite">{{ total }} ressource(s) · page {{ page }}</p>
  <div class="grid">
    <article v-for="item in items" :key="item.id" class="card">
      <span v-if="animations" class="badge">{{
        { 1: 'Validée', 2: 'À valider', 3: 'Brouillon' }[item.statut]
      }}</span>
      <h2>
        <NuxtLink :to="`${endpoint}/${item.id}`">{{
          item.titre || item.nom
        }}</NuxtLink>
      </h2>
      <p>{{ item.description?.slice(0, 220) }}</p>
      <p class="muted">
        {{ item.auteurs || catalog.label(item.fk_type_mat_id) }}
      </p>
      <small v-if="item.pertinence.requested"
        >{{ item.pertinence.matched }}/{{
          item.pertinence.requested
        }}
        mots-clés</small
      >
    </article>
  </div>
  <p v-if="!busy && !items.length">Aucune ressource pour ces critères.</p>
  <div class="actions">
    <PButton
      label="Précédent"
      :disabled="page === 1 || busy"
      @click="turn(-1)"
    /><PButton
      label="Suivant"
      :disabled="page * 20 >= total || busy"
      @click="turn(1)"
    />
  </div>
</template>
