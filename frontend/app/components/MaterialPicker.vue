<script setup>
const model = defineModel({ required: true })
const api = useApi()
const catalog = useCatalog()
const items = ref([])
const title = ref('')
const tags = ref([])
const types = ref([])
const page = ref(1)
const total = ref(0)
const error = ref('')
const busy = ref(false)
async function load(reset = false) {
  if (reset) page.value = 1
  busy.value = true
  error.value = ''
  try {
    const result = await api('/materials', {
      query: {
        kind: 'media',
        page: page.value,
        page_size: 50,
        tag: tags.value,
        type: types.value
      }
    })
    items.value = result.items
    total.value = result.total
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}
onMounted(() => load())
</script>
<template>
  <details>
    <summary>Associer des médias ({{ model.length }} sélectionné(s))</summary>
    <p v-if="error" role="alert" class="error">{{ error }}</p>
    <p>Les sélections sont conservées en changeant de page.</p>
    <TagPicker
      v-model="types"
      :items="catalog.family('ref.type_mat')"
      legend="Types"
    /><TagPicker
      v-model="tags"
      :items="catalog.family('ref.thematiques')"
      legend="Thématiques"
    /><PButton
      type="button"
      label="Filtrer les médias"
      :disabled="busy"
      @click="load(true)"
    /><label
      >Filtrer les noms de cette page<input
        v-model="title"
        type="search" /></label
    ><label
      v-for="item in items.filter((item) =>
        item.nom.toLocaleLowerCase().includes(title.toLocaleLowerCase())
      )"
      :key="item.id"
      ><input v-model="model" type="checkbox" :value="item.id" /> {{ item.nom }}
      <NuxtLink :to="`/materials/${item.id}`" target="_blank"
        >Voir la fiche</NuxtLink
      ></label
    >
    <p v-if="busy" role="status">Chargement…</p>
    <div class="actions">
      <PButton
        type="button"
        label="Précédent"
        :disabled="page === 1 || busy"
        @click="
          () => {
            page--
            load()
          }
        "
      /><span>Page {{ page }}</span
      ><PButton
        type="button"
        label="Suivant"
        :disabled="page * 50 >= total || busy"
        @click="
          () => {
            page++
            load()
          }
        "
      />
    </div>
    <p v-if="model.length">
      Identifiants sélectionnés : {{ model.join(', ') }}
    </p>
    <PButton
      v-if="model.length"
      type="button"
      class="secondary"
      label="Retirer tous les médias"
      @click="model = []"
    />
  </details>
</template>
