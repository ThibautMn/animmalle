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
      <div class="inline-form">
        <label>Libellé *<input v-model="draft.label" required maxlength="80" :disabled="busy" /></label>
        <label>Code *<input v-model="draft.code" required maxlength="200" :disabled="busy" /></label>
        <PButton
          type="submit"
          class="bare-icon"
          title="Ajouter la catégorie"
          aria-label="Ajouter la catégorie"
          :disabled="busy"
          ><ActionIcon name="add"
        /></PButton>
      </div>
    </form>
    <section v-for="group in catalog.family('')" :key="group.id" class="card">
      <div class="toolbar">
        <div class="row-actions">
          <PButton
            class="bare-icon"
            title="Ajouter une entrée"
            :aria-label="`Ajouter une entrée dans ${group.label}`"
            :aria-expanded="addingGroupId === group.id"
            :disabled="busy"
            @click="addEntry(group)"
            ><ActionIcon name="add"
          /></PButton>
          <PButton
            class="bare-icon"
            title="Modifier la catégorie"
            :aria-label="`Modifier la catégorie ${group.label}`"
            :disabled="busy"
            @click="edit(group)"
            ><ActionIcon name="edit"
          /></PButton>
          <PButton
            class="bare-icon danger"
            title="Supprimer la catégorie"
            :aria-label="`Supprimer la catégorie ${group.label}`"
            :disabled="busy"
            @click="remove(group)"
            ><ActionIcon name="delete"
          /></PButton>
        </div>
        <h2>{{ group.label }}</h2>
      </div>
      <form
        v-if="editingId === group.id"
        class="edit-entry inline-form"
        @submit.prevent="save"
      >
        <label
          >Libellé de la catégorie
          <input v-model="editedLabel" required maxlength="80" :disabled="busy" />
        </label>
        <PButton
          type="submit"
          class="bare-icon"
          title="Enregistrer"
          aria-label="Enregistrer"
          :disabled="busy"
          ><ActionIcon name="check"
        /></PButton>
        <PButton
          type="button"
          class="bare-icon"
          title="Annuler"
          aria-label="Annuler"
          :disabled="busy"
          @click="editingId = null"
          ><ActionIcon name="close"
        /></PButton>
      </form>
      <form
        v-if="addingGroupId === group.id"
        class="edit-entry"
        @submit.prevent="createEntry(group)"
      >
        <h3>Ajouter une entrée dans {{ group.label }}</h3>
        <div class="inline-form">
          <label>Libellé *<input v-model="entryDraft.label" required maxlength="80" :disabled="busy" /></label>
          <label>Code<input v-model="entryDraft.code" maxlength="200" :disabled="busy" /></label>
          <PButton
            type="submit"
            class="bare-icon"
            title="Ajouter"
            aria-label="Ajouter"
            :disabled="busy"
            ><ActionIcon name="check"
          /></PButton>
          <PButton
            type="button"
            class="bare-icon"
            title="Annuler"
            aria-label="Annuler"
            :disabled="busy"
            @click="addingGroupId = null"
            ><ActionIcon name="close"
          /></PButton>
        </div>
      </form>
      <ul class="thesaurus-entries">
        <li v-for="item in catalog.family(group.code)" :key="item.id">
          <form
            v-if="editingId === item.id"
            class="edit-entry inline-form"
            @submit.prevent="save"
          >
            <label
              >Libellé de l’entrée
              <input v-model="editedLabel" required maxlength="80" :disabled="busy" />
            </label>
            <PButton
              type="submit"
              class="bare-icon"
              title="Enregistrer"
              aria-label="Enregistrer"
              :disabled="busy"
              ><ActionIcon name="check"
            /></PButton>
            <PButton
              type="button"
              class="bare-icon"
              title="Annuler"
              aria-label="Annuler"
              :disabled="busy"
              @click="editingId = null"
              ><ActionIcon name="close"
            /></PButton>
          </form>
          <template v-else>
            <span class="row-actions">
              <PictoDialog :item="item" />
              <PButton
                class="bare-icon"
                title="Modifier le libellé"
                :aria-label="`Modifier ${item.label}`"
                :disabled="busy"
                @click="edit(item)"
                ><ActionIcon name="edit"
              /></PButton>
              <PButton
                class="bare-icon danger"
                title="Supprimer"
                :aria-label="`Supprimer ${item.label}`"
                :disabled="busy"
                @click="remove(item)"
                ><ActionIcon name="delete"
              /></PButton>
            </span>
            <span class="entry-label"
              ><PictoIcon :id="item.id" :size="24" /> {{ item.label }}</span
            >
          </template>
        </li>
      </ul>
    </section>
  </template>
</template>

<style scoped>
.toolbar {
  align-items: center;
  gap: 16px;
}

.toolbar h2 {
  margin: 0;
}

.edit-entry {
  margin-block: 8px;
}

.inline-form {
  display: flex;
  flex: 1;
  min-width: 0;
  flex-wrap: nowrap;
  align-items: flex-end;
  gap: 8px;
}

.inline-form label {
  flex: 1 1 0;
  max-width: 54ch;
  min-width: 0;
  margin: 0;
}

.inline-form button {
  flex: none;
  margin-bottom: 7px;
}

.row-actions {
  display: inline-flex;
  gap: 4px;
}

.thesaurus-entries {
  list-style: none;
  margin: 8px 0 0;
  padding: 0;
}

.thesaurus-entries li {
  display: flex;
  align-items: center;
  gap: 16px;
  padding-block: 2px;
  border-bottom: 1px solid var(--c-line);
}

.entry-label {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
</style>
