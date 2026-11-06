<script setup>
import { useSessionStore } from '~/stores/session'
const session = useSessionStore()
const api = useApi()
const catalog = useCatalog()
const draft = ref({ label: '', reference: '', code: '' })
const addingGroupId = ref(null)
const entryDraft = ref({ label: '', code: '' })
const error = ref('')
const busy = ref(false)
const editingId = ref(null)
const editedLabel = ref('')
function edit(item) {
  editingId.value = item.id
  editedLabel.value = item.label
  error.value = ''
}
async function save() {
  busy.value = true
  error.value = ''
  try {
    await api(`/thesaurus/${editingId.value}`, {
      method: 'PUT',
      body: { label: editedLabel.value },
    })
    editingId.value = null
    await load()
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}
async function load() {
  try {
    await catalog.load()
  } catch (e) {
    error.value = e.message
  }
}
function addEntry(group) {
  addingGroupId.value = group.id
  entryDraft.value = { label: '', code: '' }
  error.value = ''
}
async function createEntry(group) {
  busy.value = true
  error.value = ''
  try {
    await api('/thesaurus', {
      method: 'POST',
      body: { ...entryDraft.value, reference: group.code },
    })
    addingGroupId.value = null
    entryDraft.value = { label: '', code: '' }
    await load()
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
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
      `Supprimer « ${item.label} » ? Les mots-clés encore utilisés seront conservés.`,
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
      <h2>Ajouter une catégorie</h2>
      <label>Libellé *<input v-model="draft.label" required maxlength="80" :disabled="busy" /></label>
      <label>Code *<input v-model="draft.code" required maxlength="200" :disabled="busy" /></label>
      <PButton type="submit" label="Ajouter la catégorie" :disabled="busy" />
    </form>
    <section v-for="group in catalog.family('')" :key="group.id" class="card">
      <div class="toolbar">
        <h2>
          {{ group.label }} <small>{{ group.code }}</small>
        </h2>
        <PButton
          class="secondary delete-button"
          label="Modifier"
          :disabled="busy"
          @click="edit(group)"
        />
        <PButton
          class="danger delete-button"
          label="Supprimer la catégorie"
          :disabled="busy"
          @click="remove(group)"
        />
      </div>
      <form
        v-if="editingId === group.id"
        class="edit-entry"
        @submit.prevent="save"
      >
        <label
          >Libellé de la catégorie
          <input
            v-model="editedLabel"
            required
            maxlength="80"
            :disabled="busy"
          />
        </label>
        <PButton
          type="submit"
          class="delete-button"
          label="Enregistrer"
          :disabled="busy"
        />
        <PButton
          type="button"
          class="secondary delete-button"
          label="Annuler"
          :disabled="busy"
          @click="editingId = null"
        />
      </form>
      <ul class="thesaurus-entries">
        <li v-for="item in catalog.family(group.code)" :key="item.id">
          <form
            v-if="editingId === item.id"
            class="edit-entry"
            @submit.prevent="save"
          >
            <label
              >Libellé de l’entrée
              <input
                v-model="editedLabel"
                required
                maxlength="80"
                :disabled="busy"
              />
            </label>
            <PButton
              type="submit"
              class="delete-button"
              label="Enregistrer"
              :disabled="busy"
            />
            <PButton
              type="button"
              class="secondary delete-button"
              label="Annuler"
              :disabled="busy"
              @click="editingId = null"
            />
          </form>
          <template v-else>
            {{ item.label }}
            <PButton
              class="secondary delete-button"
              label="Modifier"
              :disabled="busy"
              @click="edit(item)"
            />
            <PButton
              class="secondary delete-button"
              label="Supprimer"
              :disabled="busy"
              @click="remove(item)"
            />
          </template>
        </li>
      </ul>
        <PButton
          type="button"
          class="secondary delete-button"
          label="Ajouter une entrée"
          :disabled="busy"
          :aria-expanded="addingGroupId === group.id"
          @click="addEntry(group)"
        />
      <form
        v-if="addingGroupId === group.id"
        class="edit-entry"
        @submit.prevent="createEntry(group)"
      >
        <h3>Ajouter une entrée dans {{ group.label }}</h3>
        <label>Libellé *<input v-model="entryDraft.label" required maxlength="80" :disabled="busy" /></label>
        <label>Code<input v-model="entryDraft.code" maxlength="200" :disabled="busy" /></label>
        <PButton type="submit" label="Ajouter" :disabled="busy" />
        <PButton
          type="button"
          class="secondary"
          label="Annuler"
          :disabled="busy"
          @click="addingGroupId = null"
        />
      </form>
    </section>
  </template>
</template>

<style scoped>
.edit-entry {
  margin-block: 8px;
}

.delete-button {
  padding: 5px 10px;
  font-size: 0.85rem;
  line-height: 1.3;
}

.thesaurus-entries li {
  padding-block: 4px;
}

.thesaurus-entries .delete-button {
  margin-left: 8px;
}
</style>
