<script setup>
import { useSessionStore } from "~/stores/session";
import { formatMinutes } from "../../lib/forms.mjs";
import { toPlainText } from "../../lib/richtext.mjs";
import { highlightParts, splitTerms } from "../../lib/search.mjs";
const props = defineProps({
  kind: { type: String, default: "animation" },
  // Mode sélection (fenêtre modale d'une animation) : pas de lien vers les fiches ni d'actions d'administration.
  picker: Boolean,
  // Identifiants déjà retenus, dont le bouton d'ajout est désactivé.
  selected: { type: Array, default: () => [] },
});
const emit = defineEmits(["pick"]);
const session = useSessionStore();
const NuxtLink = resolveComponent("NuxtLink");
const api = useApi();
const catalog = useCatalog();
const route = useRoute();
const animations = props.kind === "animation";
// La médiathèque s'affiche en vignettes, comme dans les fiches animations.
const thumbnails = props.kind === "media";
const endpoint = animations
  ? "/animations"
  : props.kind === "outil"
    ? "/outils"
    : "/media";
const heading = animations
  ? "La pédathèque"
  : props.kind === "outil"
    ? "Les outils facilitateurs"
    : "La médiathèque";
const items = ref([]);
const tags = ref([]);
const types = ref([]);
const difficulties = ref([]);
// Critères exclus (cases cochées en « - »).
const non_tags = ref([]);
const non_types = ref([]);
const non_difficulties = ref([]);
const non_statuses = ref([]);
const author = ref(route.query.auteur || "");
const authors = ref([]);
const author_open = ref(false);
const fold = (text) => text.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
const author_matches = computed(() => {
  const q = fold(author.value.trim());
  return authors.value
    .filter((name) => fold(name).includes(q) && name !== author.value)
    .sort((a, b) => {
      // Les noms sont de la forme « Prénom Nom » : tri sur le nom, puis le prénom.
      const split = (full) => {
        const parts = full.trim().split(/\s+/);
        return [parts.length > 1 ? parts.pop() : "", parts.join(" ")];
      };
      const [last_a, first_a] = split(a);
      const [last_b, first_b] = split(b);
      const options = { sensitivity: "base" };
      return (
        (last_a || first_a).localeCompare(last_b || first_b, "fr", options) ||
        first_a.localeCompare(first_b, "fr", options)
      );
    })
    .slice(0, 10);
});
const search_text = ref("");
// Critères de recherche supplémentaires : tous doivent être remplis (ET).
const extra_terms = ref([]);
// Termes de la dernière recherche aboutie, surlignés dans les résultats.
const marked_terms = ref([]);
// Découpe un texte en segments, ceux qui contiennent un terme recherché ayant hit = true.
function highlight(raw) {
  return highlightParts(toPlainText(raw), marked_terms.value);
}
const duration_min = ref(null);
const duration_max = ref(null);
const statuses = ref([]);
const status_labels = { 1: "Validée", 2: "À valider", 3: "Brouillon" };
const summary_included = computed(() => [
  ...statuses.value.map((id) => status_labels[id]),
  ...[...tags.value, ...types.value, ...difficulties.value].map((id) => catalog.label(id)),
].filter(Boolean));
const summary_excluded = computed(() => [
  ...non_statuses.value.map((id) => status_labels[id]),
  ...[...non_tags.value, ...non_types.value, ...non_difficulties.value].map((id) => catalog.label(id)),
].filter(Boolean));
const page = ref(1);
const page_size = 20;
const total = ref(0);
const busy = ref(false);
const error = ref("");
// Dernière recherche de la pédathèque, réutilisée par la fiche pour les flèches précédente/suivante
const animation_search = useState("animation_search", () => null);
// Critères de la dernière recherche de la médiathèque, pour les flèches de l'aperçu.
const media_filters = ref(null);
// Dernière recherche des outils facilitateurs, réutilisée par la fiche pour les flèches.
const outil_search = useState("outil_search", () => null);
let requestId = 0;
let duration_max_ready = false;
let skip_duration_watch = false;
async function search(reset = false) {
  if (reset) page.value = 1;
  const current = ++requestId;
  busy.value = true;
  error.value = "";
  try {
    const query = { page: page.value, page_size, tag: tags.value, non_tag: non_tags.value };
    if (animations) {
      if (author.value) query.auteur = author.value;
      const terms = [search_text.value, ...extra_terms.value]
        .map((term) => term.trim())
        .filter(Boolean);
      if (terms.length) query.q = terms;
      if (statuses.value.length) query.statut = statuses.value;
      if (non_statuses.value.length) query.non_statut = non_statuses.value;
      // Champ numérique vidé = null ou chaîne vide : borne ignorée.
      if (Number.isInteger(duration_min.value))
        query.duree_min = duration_min.value;
      if (Number.isInteger(duration_max.value))
        query.duree_max = duration_max.value;
    } else {
      query.type = types.value;
      query.non_type = non_types.value;
      if (props.kind === 'outil') {
        query.difficulte = difficulties.value;
        query.non_difficulte = non_difficulties.value;
      }
      const terms = [search_text.value, ...extra_terms.value]
        .map((term) => term.trim())
        .filter(Boolean);
      if (terms.length) query.q = terms;
    }
    const result = await api(endpoint, { query });
    if (current === requestId) {
      if (animations) {
        const { page: _page, page_size: _size, ...filters } = query;
        animation_search.value = filters;
      } else if (thumbnails) {
        const { page: _page, page_size: _size, ...filters } = query;
        media_filters.value = filters;
      } else if (props.kind === "outil" && !props.picker) {
        const { page: _page, page_size: _size, ...filters } = query;
        outil_search.value = filters;
      }
      marked_terms.value = splitTerms(query.q || []);
      items.value = result.items;
      total.value = result.total;
      // Bornes par défaut : la plus courte et la plus longue animation (sans effet sur la liste).
      if (animations && !duration_max_ready) {
        duration_max_ready = true;
        if (result.duree_max > 0 && duration_max.value === null) {
          skip_duration_watch = true;
          duration_max.value = result.duree_max;
          if (duration_min.value === null) duration_min.value = result.duree_min;
        }
      }
    }
  } catch (e) {
    if (current === requestId) error.value = e.message;
  } finally {
    if (current === requestId) busy.value = false;
  }
}
const { confirmDelete } = useConfirmDelete();
async function remove(item) {
  if (
    !(await confirmDelete(
      `Supprimer ${props.kind === "outil" ? "cet outil" : "ce média"} et détacher ses associations ?`,
    ))
  )
    return;
  try {
    await api(`${endpoint}/${item.id}`, { method: "DELETE" });
    if (items.value.length === 1 && page.value > 1) page.value--;
    await search();
  } catch (e) {
    error.value = e.message;
  }
}
let timer;
watch(
  [author, search_text, extra_terms, statuses, non_statuses, tags, non_tags, types, non_types, difficulties, non_difficulties, duration_min, duration_max],
  () => {
    if (skip_duration_watch) {
      skip_duration_watch = false;
      return;
    }
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
  if (!props.picker) window.scrollTo({ top: 0, behavior: "smooth" });
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
  <div v-if="!picker" class="toolbar">
    <h1>{{ heading }}</h1>
    <NuxtLink
      class="button"
      :to="animations ? '/animations/nouveau' : `/materials/nouveau?kind=${kind}`"
      >{{
        animations
          ? "Créer une animation"
          : kind === "outil"
            ? "Créer un outil"
            : "Importer une ressource"
      }}</NuxtLink
    >
  </div>
  <div
    :class="[
      'catalog-layout',
      animations && 'with-sidebar',
      picker && 'catalog-picker',
      kind === 'outil' && 'tools-tint',
    ]"
  >
    <form class="card filters" @submit.prevent="search(true)">
      <div class="search-field">
        <label
          >Recherche<span class="search-row"
            ><input
              v-model="search_text"
              type="search"
              maxlength="100"
              :placeholder="
                animations
                  ? 'Titre, description ou objectifs…'
                  : 'Nom, description, type, thématique, matériel…'
              "
            />
            <PButton
              v-if="search_text.trim()"
              type="button"
              class="secondary icon-button"
              title="Ajouter un critère de recherche (ET)"
              aria-label="Ajouter un critère de recherche"
              label="+"
              @click="extra_terms.push('')"
          /></span>
        </label>
        <div
          v-for="(term, index) in extra_terms"
          :key="index"
          class="search-row"
        >
          <input
            v-model="extra_terms[index]"
            type="search"
            maxlength="100"
            placeholder="ET autre critère…"
            :aria-label="`Critère de recherche ${index + 2}`"
          />
          <PButton
            type="button"
            class="secondary icon-button"
            title="Retirer ce critère"
            aria-label="Retirer ce critère"
            label="×"
            @click="extra_terms.splice(index, 1)"
          />
        </div>
      </div>
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
        v-model:excluded="non_types"
        :items="
          catalog.family(kind === 'outil' ? 'ref.type_outil' : 'ref.type_mat')
        "
        :legend="kind === 'outil' ? 'Type d\'outil' : 'Types de ressources'"
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
          ><TriCheck v-model="statuses" v-model:excluded="non_statuses" :value="value" />{{
            label
          }}</label
        >
      </fieldset>
      <TagPicker
        v-if="kind === 'outil'"
        v-model="difficulties"
        v-model:excluded="non_difficulties"
        :items="catalog.family('ref.difficulte')"
        legend="Difficulté"
      />
      <TagPicker
        v-for="group in animations
          ? [
              'ref.thematiques',
              'ref.lieux',
              'ref.saison',
              'ref.public',
              'ref.duree',
            ]
          : kind === 'outil'
            ? []
            : ['ref.thematiques']"
        :key="group"
        v-model="tags"
        v-model:excluded="non_tags"
        :items="catalog.family(group)"
        :legend="
          catalog.items.value.find((item) => item.code === group)?.label ||
          group.replace('ref.', '')
        "
      >
        <div v-if="group === 'ref.duree'" class="duration-range">
          <span class="duration-range-title">Durée totale des séquences</span>
          <div class="duration-range-fields">
            <label
              >Entre
              <DurationStepper v-model="duration_min" :max="100000" />
            </label>
            <label
              >et
              <DurationStepper v-model="duration_max" :max="100000" />
              minutes
            </label>
          </div>
        </div>
      </TagPicker>
    </form>
    <div class="catalog-results">
      <p v-if="error" role="alert" class="error">{{ error }}</p>
      <div v-if="busy" class="loading-overlay">
        <p role="status" class="loading-status">
          <span class="loader-bar" aria-hidden="true" />Recherche en cours…
        </p>
      </div>
      <div class="results-content" :inert="busy" :aria-busy="busy">
        <FilterSummary :included="summary_included" :excluded="summary_excluded" />
        <PaginationNav
          :page="page"
          :page-count="page_count"
          :entries="page_entries"
          :busy="busy"
          @go="go"
        />
        <SequenceMedia
          v-if="thumbnails"
          :items="items"
          :query="media_filters"
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
        <div v-else-if="animations" class="resource-list cards-list">
          <article v-for="item in items" :key="item.id" class="card">
            <span class="badge" :class="`statut-${item.statut}`">{{
              { 1: "Validée", 2: "À valider", 3: "Brouillon" }[item.statut]
            }}</span>
            <div class="card-title-row">
              <h2>
                <NuxtLink :to="`${endpoint}/${item.id}`"
                  ><template
                    v-for="(part, index) in highlight(item.titre)"
                    :key="index"
                    ><mark v-if="part.hit">{{ part.text }}</mark
                    ><template v-else>{{ part.text }}</template></template
                  ></NuxtLink
                >
              </h2>
              <span class="duration-badges">
                <span
                  v-if="catalog.label(item.fk_duree_id)"
                  class="badge duration-badge"
                  title="Durée totale"
                  >{{ catalog.label(item.fk_duree_id) }}</span
                >
                <span
                  v-if="formatMinutes(item.duree_minutes)"
                  class="badge duration-badge"
                  title="Durée cumulée des séquences"
                  >{{ formatMinutes(item.duree_minutes) }}</span
                >
              </span>
            </div>
            <p class="pictos">
              <PictoIcon v-for="tag in item.tags" :id="tag" :key="tag" />
            </p>
            <p class="prose">
              <template v-if="item.description"
                ><template
                  v-for="(part, index) in highlight(item.description)"
                  :key="index"
                  ><mark v-if="part.hit">{{ part.text }}</mark
                  ><template v-else>{{ part.text }}</template></template
                ></template
              ><template v-else>Non renseignée</template>
            </p>
            <p
              v-if="highlight(item.objectifs).some((part) => part.hit)"
              class="prose"
            >
              <strong>Objectifs : </strong
              ><template
                v-for="(part, index) in highlight(item.objectifs)"
                :key="index"
                ><mark v-if="part.hit">{{ part.text }}</mark
                ><template v-else>{{ part.text }}</template></template
              >
            </p>
            <p class="muted">{{ item.auteurs }}</p>
            <small v-if="item.pertinence?.requested"
              >{{ item.pertinence?.matched }}/{{
                item.pertinence?.requested
              }}
              mots-clés</small
            >
          </article>
        </div>
        <div v-else class="tool-grid">
          <article v-for="item in items" :key="item.id" class="card tool-card">
            <header class="tool-head">
              <h2>
                <component
                  :is="picker ? 'span' : NuxtLink"
                  v-bind="picker ? {} : { to: `/materials/${item.id}?kind=outil` }"
                  ><template
                    v-for="(part, index) in highlight(item.titre || item.nom)"
                    :key="index"
                    ><mark v-if="part.hit">{{ part.text }}</mark
                    ><template v-else>{{ part.text }}</template></template
                  ></component
                >
              </h2>
              <span class="tool-badges">
                <span
                  v-if="catalog.label(item.fk_type_outil_id)"
                  class="badge duration-badge"
                  title="Catégorie de l'outil"
                  >{{ catalog.label(item.fk_type_outil_id) }}</span
                >
                <span
                  v-if="catalog.label(item.difficulte_id)"
                  class="badge duration-badge"
                  title="Difficulté"
                  >{{ catalog.label(item.difficulte_id) }}</span
                >
              </span>
            </header>
            <p class="tool-desc prose">
              <template v-if="toPlainText(item.description)"><template
                v-for="(part, index) in highlight(item.description)"
                :key="index"
                ><mark v-if="part.hit">{{ part.text }}</mark
                ><template v-else>{{ part.text }}</template></template
              ></template
              ><template v-else>Pas de description</template>
            </p>
            <p v-if="toPlainText(item.materiel)" class="tool-line">
              <strong>Matériel :</strong> <template
                v-for="(part, index) in highlight(item.materiel)"
                :key="index"
                ><mark v-if="part.hit">{{ part.text }}</mark
                ><template v-else>{{ part.text }}</template></template
              >
            </p>
            <p v-if="toPlainText(item.variante)" class="tool-line">
              <strong>Variante :</strong> <template
                v-for="(part, index) in highlight(item.variante)"
                :key="index"
                ><mark v-if="part.hit">{{ part.text }}</mark
                ><template v-else>{{ part.text }}</template></template
              >
            </p>
            <footer class="tool-foot">
              <small class="muted"
                >Modifiée le {{ item.date_modif || "—" }}</small
              >
                <div v-if="picker" class="actions resource-actions">
                  <PButton
                    type="button"
                    :label="
                      selected.includes(item.id)
                        ? 'Déjà dans l\'animation'
                        : 'Ajouter dans les séquences'
                    "
                    :disabled="selected.includes(item.id)"
                    @click="emit('pick', item)"
                  />
                </div>
                <div v-else class="actions resource-actions">
                  <DownloadButton
                    data-tooltip="Exporte l'outil et ses fichiers dans une archive ZIP"
                    :path="`${endpoint}/${item.id}/download`"
                    :filename="`${item.nom}.zip`"
                    label="Exporter en ZIP"
                    icon="pi-box"
                  />
                  <NuxtLink
                    v-if="session.is_admin"
                    class="button icon-button"
                    :to="`/materials/${item.id}?kind=${kind}&edit=1`"
                    data-tooltip="Ouvre la fiche en mode modification"
                    aria-label="Modifier la ressource"
                    ><ActionIcon name="edit"
                  /></NuxtLink>
                  <PButton
                    v-if="session.is_admin"
                    class="danger icon-button"
                    data-tooltip="Supprime définitivement l'outil après confirmation"
                    aria-label="Supprimer la ressource"
                    @click="remove(item)"
                    ><ActionIcon name="delete"
                  /></PButton>
                </div>
            </footer>
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
