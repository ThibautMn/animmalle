<script setup>
import { useSessionStore } from '~/stores/session'
const route = useRoute()
const api = useApi()
const session = useSessionStore()
const catalog = useCatalog()
const page = ref(null)
const content = ref('')
const editing = ref(false)
const busy = ref(true)
const error = ref('')
const notice = ref('')
async function load() {
  try {
    await catalog.load()
    page.value = await api(`/pages/${route.params.name}`)
    content.value = page.value.contenu
  } catch (e) {
    if (e.status === 404 && session.is_admin) {
      page.value = { contenu: '', html: '', documents: [] }
      editing.value = true
    } else error.value = e.message
  } finally {
    busy.value = false
  }
}
async function save() {
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    const result = await api(`/pages/${route.params.name}`, {
      method: 'PUT',
      body: { contenu: content.value }
    })
    editing.value = false
    await load()
    notice.value =
      result.notification === 'failed'
        ? 'Page enregistrée ; la notification par courriel a échoué.'
        : 'Page enregistrée.'
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}
onBeforeRouteLeave(
  () => !editing.value || window.confirm('Quitter sans enregistrer la page ?')
)
onMounted(load)
</script>
<template>
  <NuxtLink to="/outils">← Outils facilitateurs</NuxtLink>
  <h1>
    {{
      catalog
        .family('ref.type_outil')
        .find((item) => item.code === route.params.name)?.label ||
      route.params.name
    }}
  </h1>
  <p v-if="error" role="alert" class="error">{{ error }}</p>
  <p v-if="notice" role="status">{{ notice }}</p>
  <p v-if="busy" role="status">Chargement…</p>
  <template v-if="page"
    ><form v-if="editing" @submit.prevent="save">
      <label
        >Contenu Markdown<textarea
          v-model="content"
          required
          maxlength="1000000"
          rows="24"
        /></label
      ><PButton
        type="submit"
        label="Enregistrer la page"
        :disabled="busy"
      /><PButton
        type="button"
        class="secondary"
        label="Annuler"
        @click="
          () => {
            editing = false
            content = page.contenu
          }
        "
      />
    </form>
    <template v-else
      ><PButton
        v-if="session.is_admin"
        label="Modifier cette page"
        @click="editing = true"
      />
      <div class="card page-html" v-html="page.html" />
      <h2>Documents associés</h2>
      <article v-for="item in page.documents" :key="item.id" class="card">
        <NuxtLink :to="`/materials/${item.id}`">{{ item.nom }}</NuxtLink>
        <p>{{ item.description }}</p>
      </article></template
    ></template
  >
</template>
