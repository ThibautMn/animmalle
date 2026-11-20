<script setup>
import { useSessionStore } from '~/stores/session'
const session = useSessionStore()
const firstName = computed(() => (session.user?.name || '').split(' ')[0])
const api = useApi()
const config = useRuntimeConfig()
const items = ref([])
const error = ref('')
const busy = ref(false)
const input = ref(null)
const imageUrl = (name) => `${config.public.apiBase}/banners/${encodeURIComponent(name)}/image`
// L'image est cadrée comme sur la page d'accueil : seule sa hauteur (0 % haut, 100 % bas) se règle.
async function load() {
  try {
    items.value = (await api('/banners')).items
  } catch (e) {
    error.value = e.message
  }
}
let timers = {}
function moved(item) {
  // enregistrement après une courte pause, pour ne pas envoyer une requête par pixel de curseur
  clearTimeout(timers[item.name])
  timers[item.name] = setTimeout(async () => {
    error.value = ''
    try {
      await api(`/banners/${encodeURIComponent(item.name)}`, {
        method: 'PUT',
        body: { position: Number(item.position) },
      })
    } catch (e) {
      error.value = e.message
    }
  }, 400)
}
async function add(event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file) return
  busy.value = true
  error.value = ''
  try {
    const body = new FormData()
    body.append('file', file)
    await api('/banners', { method: 'POST', body })
    await load()
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}
const { confirmDelete } = useConfirmDelete()
async function remove(item) {
  if (!(await confirmDelete(`Supprimer la bannière « ${item.name} » ?`))) return
  error.value = ''
  try {
    await api(`/banners/${encodeURIComponent(item.name)}`, { method: 'DELETE' })
    await load()
  } catch (e) {
    error.value = e.message
  }
}
onMounted(load)
onBeforeUnmount(() => Object.values(timers).forEach(clearTimeout))
</script>
<template>
  <div>
    <div class="toolbar">
      <p class="muted">
        Images affichées au hasard en haut de la page d’accueil. Réglez la
        hauteur du cadrage avec le curseur.
      </p>
      <input
        ref="input"
        type="file"
        accept="image/jpeg,image/png,image/webp"
        hidden
        @change="add"
      />
      <PButton
        type="button"
        label="Ajouter une bannière"
        :disabled="busy"
        @click="input.click()"
      />
    </div>
    <p v-if="error" role="alert" class="error">{{ error }}</p>
    <p v-if="!items.length" class="muted">Aucune bannière.</p>
    <ul class="banner-list">
      <li v-for="item in items" :key="item.name" class="card">
        <HomeHero
          class="banner-preview"
          :first-name="firstName"
          :image="imageUrl(item.name)"
          :position="Number(item.position)"
        />
        <div class="banner-controls">
          <label
            >Hauteur dans le cadre
            <input
              v-model="item.position"
              type="range"
              min="0"
              max="100"
              @input="moved(item)"
            />
          </label>
          <small class="muted">{{ item.name }}</small>
          <PButton
            type="button"
            class="linkbtn"
            label="Supprimer"
            @click="remove(item)"
          />
        </div>
      </li>
    </ul>
  </div>
</template>
<style scoped>
.banner-list {
  list-style: none;
  margin: 16px 0 0;
  padding: 0;
  display: grid;
  gap: 16px;
}
.banner-preview.hero {
  margin: 0;
  border-radius: var(--radius);
}
.banner-controls {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 16px;
  margin-top: 10px;
}
.banner-controls label {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: 1;
  min-width: 240px;
}
.banner-controls input[type='range'] {
  flex: 1;
  padding: 0;
}
</style>
