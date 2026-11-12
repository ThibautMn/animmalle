<script setup>
import { useSessionStore } from "~/stores/session";
const props = defineProps({ kind: { type: String, default: "animation" } });
const session = useSessionStore();
const api = useApi();
const catalog = useCatalog();
const route = useRoute();
const animations = props.kind === "animation";
const endpoint = animations ? "/animations" : "/materials";
const heading = animations
  ? "La pédathèque"
  : props.kind === "outil"
    ? "Les outils facilitateurs"
    : "La médiathèque";
const items = ref([]);
const tags = ref([]);
const types = ref([]);
const author = ref(route.query.auteur || "");
const authors = ref([]);
const author_open = ref(false);
const author_matches = computed(() => {
  const q = author.value.trim().toLowerCase();
  return authors.value
    .filter((name) => name.toLowerCase().includes(q) && name !== author.value)
    .slice(0, 10);
});
const search_text = ref("");
const statuses = ref([]);
const page = ref(1);
const page_size = 20;
const total = ref(0);
const busy = ref(false);
const error = ref("");
let requestId = 0;
async function search(reset = false) {
  if (reset) page.value = 1;
  const current = ++requestId;
  busy.value = true;
  error.value = "";
  try {
    const query = { page: page.value, page_size, tag: tags.value };
    if (animations) {
      if (author.value) query.auteur = author.value;
      if (search_text.value.trim()) query.q = search_text.value.trim();
      if (statuses.value.length) query.statut = statuses.value;
    } else {
      query.kind = props.kind;
      query.type = types.value;
    }
    const result = await api(endpoint, { query });
    if (current === requestId) {
      items.value = result.items;
      total.value = result.total;
    }
  } catch (e) {
    if (current === requestId) error.value = e.message;
  } finally {
    if (current === requestId) busy.value = false;
  }
}
async function remove(item) {
  if (!window.confirm("Supprimer cette notice et détacher ses associations ?"))
    return;
  try {
    await api(`/materials/${item.id}`, { method: "DELETE" });
    if (items.value.length === 1 && page.value > 1) page.value--;
    await search();
  } catch (e) {
    error.value = e.message;
  }
}
let timer;
watch(
  [author, search_text, statuses, tags, types],
  () => {
    clearTimeout(timer);
    timer = setTimeout(() => search(true), 300);
  },
  { deep: true },
);
onBeforeUnmount(() => clearTimeout(timer));
const page_count = computed(() =>
  Math.max(1, Math.ceil(total.value / page_size)),
);
// Numéros affichés : première, dernière, page courante et ses voisines
const page_entries = computed(() => {
  const last = page_count.value;
  const wanted = new Set([1, last]);
  for (let n = page.value - 1; n <= page.value + 1; n++)
    if (n >= 1 && n <= last) wanted.add(n);
  const entries = [];
  let previous = 0;
  for (const n of [...wanted].sort((a, b) => a - b)) {
    if (n - previous === 2) entries.push(previous + 1);
    else if (n - previous > 2) entries.push(null);
    entries.push(n);
    previous = n;
  }
  return entries;
});
async function go(target) {
  if (target < 1 || target > page_count.value || target === page.value) return;
  page.value = target;
  await search();
  window.scrollTo({ top: 0, behavior: "smooth" });
}
onMounted(async () => {
  await search();
  try {
    await catalog.load();
    if (animations) authors.value = (await api("/authors")).items;
  } catch (e) {
    error.value = e.message;
  }
});
</script>
<template>
  <div class="toolbar">
    <h1>{{ heading }}</h1>
    <NuxtLink
      class="button"
      :to="`${endpoint}/nouveau${animations ? '' : '?kind=' + kind}`"
      >{{
        animations ? "Créer une animation" : "Importer une ressource"
      }}</NuxtLink
    >
  </div>
  <div :class="['catalog-layout', animations && 'with-sidebar']">
    <form class="card filters" @submit.prevent="search(true)">
      <label v-if="animations" class="search-field"
        >Recherche<input
          v-model="search_text"
          type="search"
          maxlength="100"
          placeholder="Titre ou description…"
      /></label>
      <div v-if="animations" class="author-row">
        <label
          >Auteur<span class="author-combo"
            ><input
              v-model="author"
              autocomplete="off"
              @focus="author_open = true"
              @input="author_open = true"
              @blur="author_open = false"
              @keydown.esc="author_open = false"
            />
            <ul v-if="author_open && author_matches.length" class="author-popup">
              <li
                v-for="name in author_matches"
                :key="name"
                @mousedown.prevent="
                  () => {
                    author = name;
                    author_open = false;
                  }
                "
              >
                {{ name }}
              </li>
            </ul></span
          >
        </label>
        <PButton
          type="button"
          class="secondary"
          label="Mes animations"
          @click="
            () => {
              author = session.user.name;
              search(true);
            }
          "
        />
      </div>
      <TagPicker
        v-if="!animations"
        v-model="types"
        :items="
          catalog.family(kind === 'outil' ? 'ref.type_outil' : 'ref.type_mat')
        "
        legend="Types de ressources"
      />
      <fieldset v-if="animations" class="status-box">
        <legend>Statut</legend>
        <label
          v-for="[value, label] in [
            ['1', 'Validée'],
            ['2', 'À valider'],
            ['3', 'Brouillon'],
          ]"
          :key="value"
          class="check"
          ><input v-model="statuses" type="checkbox" :value="value" />{{
            label
          }}</label
        >
      </fieldset>
      <TagPicker
        v-for="group in animations
          ? [
              'ref.thematiques',
              'ref.lieux',
              'ref.saison',
              'ref.public',
              'ref.duree',
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
    </form>
    <div class="catalog-results">
      <p v-if="error" role="alert" class="error">{{ error }}</p>
      <div v-if="busy" class="loading-overlay">
        <p role="status" class="loading-status">
          <span class="loader-bar" aria-hidden="true" />Recherche en cours…
        </p>
      </div>
      <div class="results-content" :inert="busy" :aria-busy="busy">
        <PaginationNav
          :page="page"
          :page-count="page_count"
          :entries="page_entries"
          :busy="busy"
          @go="go"
        />
        <div :class="['resource-list', animations && 'cards-list']">
          <article v-for="item in items" :key="item.id" class="card">
            <span v-if="animations" class="badge">{{
              { 1: "Validée", 2: "À valider", 3: "Brouillon" }[item.statut]
            }}</span>
            <h2>
              <NuxtLink :to="`${endpoint}/${item.id}`">{{
                item.titre || item.nom
              }}</NuxtLink>
            </h2>
            <p class="pictos">
              <PictoIcon
                v-for="tag in animations ? item.tags : item.thematiques"
                :id="tag"
                :key="tag"
              />
            </p>
            <template v-if="!animations">
              <div class="actions resource-actions">
                <MediaPreview v-if="item.has_file" :id="item.id" icon />
                <DownloadButton
                  v-if="item.has_file"
                  :path="`/materials/${item.id}/file`"
                  label="Télécharger la pièce jointe"
                  icon="download"
                />
                <DownloadButton
                  :path="`/materials/${item.id}/download`"
                  :filename="`${item.nom}.zip`"
                  label="Exporter en ZIP"
                  icon="zip"
                />
                <NuxtLink
                  v-if="session.is_admin"
                  class="button icon-button"
                  :to="`/materials/${item.id}?edit=1`"
                  title="Modifier la ressource"
                  aria-label="Modifier la ressource"
                  ><ActionIcon name="edit"
                /></NuxtLink>
                <PButton
                  v-if="session.is_admin"
                  class="danger icon-button"
                  title="Supprimer la ressource"
                  aria-label="Supprimer la ressource"
                  @click="remove(item)"
                  ><ActionIcon name="delete"
                /></PButton>
              </div>
              <dl class="resource-details">
                <template
                  v-for="[key, label] in [
                    ['description', 'Description / Consigne'],
                    ['variante', 'Variante'],
                    ['materiel', 'Matériel'],
                    ['localisation', 'Localisation'],
                  ]"
                  :key="key"
                >
                  <dt>{{ label }}</dt>
                  <dd class="prose">{{ item[key] || "Non renseigné" }}</dd>
                </template>
                <dt>Thématiques</dt>
                <dd>
                  {{
                    item.thematiques.map(catalog.label).join(" · ") ||
                    "Non renseignées"
                  }}
                </dd>
                <dt>Difficulté</dt>
                <dd>
                  {{ catalog.label(item.difficulte_id) || "Non renseignée" }}
                </dd>
                <dt>Type de pièce jointe</dt>
                <dd>
                  {{
                    catalog.label(item.fk_type_mat_outil_id) ||
                    catalog.label(item.fk_type_mat_id)
                  }}
                </dd>
                <dt>Modifiée le</dt>
                <dd>{{ item.date_modif || "Non renseigné" }}</dd>
                <dt>Pièce jointe</dt>
                <dd>{{ item.has_file ? "Disponible" : "Aucune" }}</dd>
              </dl>
            </template>
            <p v-else class="prose">
              {{ item.description || "Non renseignée" }}
            </p>
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
        <PaginationNav
          :page="page"
          :page-count="page_count"
          :entries="page_entries"
          :busy="busy"
          @go="go"
        />
      </div>
    </div>
  </div>
</template>
