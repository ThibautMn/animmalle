<script setup>
import { useSessionStore } from '~/stores/session'
const session = useSessionStore()
const api = useApi()
const catalog = useCatalog()
const draft = ref({ label: '', reference: '', code: '' })
const error = ref('')
const busy = ref(false)
async function load() {
  try {
    await catalog.load()
  } catch (e) {
    error.value = e.message
  }
}
async function create() {
  busy.value = true
  error.value = ''
  try {
    await api('/thesaurus', { method: 'POST', body: draft.value })
    draft.value = { label: '', reference: '', code: '' }
    await load()
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}
async function remove(item) {
  if (
    !window.confirm(
      `Supprimer « ${item.label} » ? Les mots-clés encore utilisés seront conservés.`
    )
  )
    return
  busy.value = true
  error.value = ''
  try {
    await api(`/thesaurus/${item.id}`, { method: 'DELETE' })
    await load()
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}
onMounted(load)
</script>
<template>
  <h1>Le thésaurus</h1>
  <p v-if="!session.is_admin" role="alert">
    Cette page est réservée aux administrateurs.
  </p>
  <template v-else
    ><p v-if="error" role="alert" class="error">{{ error }}</p>
    <form class="card" @submit.prevent="create">
      <h2>Ajouter une entrée</h2>
      <label
        >Libellé *<input v-model="draft.label" required maxlength="80" /></label
      ><label
        >Catégorie<select v-model="draft.reference">
          <option value="">Nouvelle catégorie</option>
          <option
            v-for="item in catalog.family('')"
            :key="item.id"
            :value="item.code"
          >
            {{ item.label }}
          </option>
        </select></label
      ><label
        >Code {{ draft.reference ? '' : '*'
        }}<input
          v-model="draft.code"
          :required="!draft.reference"
          maxlength="200" /></label
      ><PButton type="submit" label="Ajouter" :disabled="busy" />
    </form>
    <section v-for="group in catalog.family('')" :key="group.id" class="card">
      <div class="toolbar">
        <h2>
          {{ group.label }} <small>{{ group.code }}</small>
        </h2>
        <PButton
          class="danger"
          label="Supprimer la catégorie"
          :disabled="busy"
          @click="remove(group)"
        />
      </div>
      <ul>
        <li v-for="item in catalog.family(group.code)" :key="item.id">
          {{ item.label }}
          <PButton
            class="secondary"
            label="Supprimer"
            :disabled="busy"
            @click="remove(item)"
          />
        </li>
      </ul></section
  ></template>
</template>
