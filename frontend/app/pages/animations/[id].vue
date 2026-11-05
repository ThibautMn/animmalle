<script setup>
import { useSessionStore } from '~/stores/session'
import {
  animationFields,
  sequenceFields,
  sequenceRefs,
  newSequence,
  animationPayload,
  moveSequence
} from '../../../lib/forms.mjs'
const window = globalThis.window
const route = useRoute()
const api = useApi()
const session = useSessionStore()
const catalog = useCatalog()
const creating = route.params.id === 'nouveau'
const item = ref({
  titre: '',
  statut: 3,
  lieu: '',
  fk_duree_id: null,
  tags: [],
  sequences: [],
  ...Object.fromEntries(animationFields.map(([key]) => [key, '']))
})
const draft = ref(null)
const comments = ref([])
const comment = ref('')
const author = ref('')
const suggestions = ref([])
const error = ref('')
const busy = ref(true)
const editing = ref(creating)
const canEdit = computed(
  () =>
    creating ||
    session.is_admin ||
    (item.value.auteurs === session.user?.name && item.value.statut !== 1)
)
const path = `/animations/${route.params.id}`
async function load() {
  error.value = ''
  busy.value = true
  try {
    await catalog.load()
    if (!creating) {
      item.value = await api(path)
      comments.value = (await api(`${path}/comments`)).items
      author.value = item.value.auteurs
    }
    draft.value = structuredClone(toRaw(item.value))
    // La durée est envoyée par son champ dédié ; le backend l’ajoute aux tags.
    const durationIds = new Set(
      catalog.family('ref.duree').map((tag) => tag.id)
    )
    draft.value.tags = draft.value.tags.filter((id) => !durationIds.has(id))
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}
async function save() {
  busy.value = true
  error.value = ''
  try {
    const body = animationPayload(draft.value)
    const durationIds = new Set(catalog.family('ref.duree').map(tag => tag.id))
    body.tags = body.tags.filter(id => !durationIds.has(id))
    const result = await api(creating ? '/animations' : path, {
      method: creating ? 'POST' : 'PUT',
      body
    })
    if (creating) {
      editing.value = false
      await navigateTo(`/animations/${result.id}`)
    } else {
      editing.value = false
      await load()
    }
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}
async function action(suffix, method, body) {
  busy.value = true
  error.value = ''
  try {
    await api(path + suffix, { method, body })
    await load()
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}
async function remove() {
  if (
    !window.confirm(
      'Supprimer définitivement cette animation et ses commentaires ?'
    )
  )
    return
  busy.value = true
  error.value = ''
  try {
    await api(path, { method: 'DELETE' })
    await navigateTo('/animations')
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}
function removeSequence(index) {
  if (window.confirm('Retirer cette séquence de l’animation ?'))
    draft.value.sequences.splice(index, 1)
}
function cancel() {
  draft.value = structuredClone(toRaw(item.value))
  editing.value = false
}
onBeforeRouteLeave(
  () =>
    !editing.value ||
    window.confirm('Quitter sans enregistrer les modifications ?')
)
onMounted(load)
</script>
<template>
  <NuxtLink to="/animations">← Pédathèque</NuxtLink>
  <p v-if="error" role="alert" class="error">{{ error }}</p>
  <p v-if="busy" role="status">Chargement…</p>
  <template v-if="draft">
    <form v-if="editing" @submit.prevent="save">
      <h1>{{ creating ? 'Créer une animation' : 'Modifier l’animation' }}</h1>
      <p>Le titre et les références des séquences sont obligatoires.</p>
      <fieldset :disabled="busy">
        <label
          >Titre *<input
            v-model="draft.titre"
            required
            maxlength="100" /></label
        ><label>Lieu<input v-model="draft.lieu" /></label
        ><RefSelect
          v-model="draft.fk_duree_id"
          :items="catalog.family('ref.duree')"
          label="Durée totale"
        /><TextFields v-model="draft" :fields="animationFields" /><TagPicker
          v-for="group in [
            'ref.thematiques',
            'ref.lieux',
            'ref.saison',
            'ref.public'
          ]"
          :key="group"
          v-model="draft.tags"
          :items="catalog.family(group)"
          :legend="
            catalog.items.value.find((tag) => tag.code === group)?.label ||
            group
          "
        />
        <h2>Déroulé de l’animation</h2>
        <section
          v-for="(seq, index) in draft.sequences"
          :key="seq.id || index"
          class="card"
        >
          <h3>Séquence {{ index + 1 }}</h3>
          <div class="actions">
            <PButton
              type="button"
              class="secondary"
              label="Monter"
              :disabled="index === 0"
              @click="moveSequence(draft.sequences, index, -1)"
            /><PButton
              type="button"
              class="secondary"
              label="Descendre"
              :disabled="index === draft.sequences.length - 1"
              @click="moveSequence(draft.sequences, index, 1)"
            /><PButton
              type="button"
              class="danger"
              label="Retirer la séquence"
              @click="removeSequence(index)"
            />
          </div>
          <label
            >Titre de la séquence *<input
              v-model="seq.titre"
              required
              maxlength="100"
          /></label>
          <div class="grid">
            <RefSelect
              v-for="[key, family, label] in sequenceRefs"
              :key="key"
              v-model="seq[key]"
              :items="catalog.family(family)"
              :label="label + ' *'"
              required
            />
          </div>
          <TextFields
            v-model="draft.sequences[index]"
            :fields="sequenceFields"
          /><MaterialPicker v-model="seq.materiel" />
        </section>
        <PButton
          type="button"
          class="secondary"
          label="Ajouter une séquence"
          @click="draft.sequences.push(newSequence())"
        /><label
          >État<select v-model="draft.statut">
            <option :value="3">Brouillon</option>
            <option :value="2">Complète, à valider</option>
            <option v-if="session.is_admin" :value="1">Validée</option>
          </select></label
        ><PButton type="submit" label="Enregistrer" /><PButton
          v-if="!creating"
          type="button"
          class="secondary"
          label="Annuler"
          @click="cancel"
        />
      </fieldset>
    </form>
    <template v-else
      ><div class="toolbar">
        <h1>{{ item.titre }}</h1>
        <span class="badge">{{
          { 1: 'Validée', 2: 'À valider', 3: 'Brouillon' }[item.statut]
        }}</span>
      </div>
      <p>
        {{ item.auteurs }} · {{ item.date_modif }} ·
        {{ catalog.label(item.fk_duree_id) }}
      </p>
      <div class="actions">
        <PButton
          v-if="canEdit"
          label="Modifier"
          :disabled="busy"
          @click="editing = true"
        /><DownloadButton
          :path="`${path}/download`"
          :filename="`${item.titre}.zip`"
          label="Exporter en ZIP / ODT"
        /><PButton
          class="secondary"
          label="Imprimer"
          @click="window.print()"
        /><PButton
          v-if="session.is_admin && item.statut !== 1"
          label="Valider"
          :disabled="busy"
          @click="action('/validate', 'POST')"
        /><PButton
          v-if="canEdit"
          class="danger"
          label="Supprimer"
          :disabled="busy"
          @click="remove"
        />
      </div>
      <p>Lieu : {{ item.lieu }}</p>
      <p>{{ item.tags.map(catalog.label).filter(Boolean).join(' · ') }}</p>
      <section v-for="[key, label] in animationFields" :key="key" class="card">
        <h2>{{ label }}</h2>
        <p class="prose">{{ item[key] || 'Non renseigné' }}</p>
      </section>
      <h2>Les séquences</h2>
      <section
        v-for="(seq, index) in item.sequences"
        :key="seq.id"
        class="card"
      >
        <h3>{{ index + 1 }}. {{ seq.titre }}</h3>
        <p>
          {{ sequenceRefs.map(([key]) => catalog.label(seq[key])).join(' · ') }}
        </p>
        <div v-for="[key, label] in sequenceFields" :key="key">
          <h4>{{ label }}</h4>
          <p class="prose">{{ seq[key] }}</p>
        </div>
        <p>
          Médias :
          <NuxtLink
            v-for="id in seq.materiel"
            :key="id"
            :to="`/materials/${id}`"
            >Ressource {{ id }} ·
          </NuxtLink>
        </p>
      </section>
      <form
        v-if="session.is_admin"
        class="card"
        @submit.prevent="action('/author', 'PUT', { auteurs: author })"
      >
        <h2>Réattribuer la fiche</h2>
        <label
          >Auteur<input
            v-model="author"
            list="users"
            required
            maxlength="200" /></label
        ><PButton
          type="button"
          class="secondary"
          label="Chercher dans l’annuaire"
          :disabled="author.trim().length < 2 || busy"
          @click="
            async () => {
              try {
                suggestions = (await api('/users', { query: { q: author } }))
                  .items
              } catch (e) {
                error = e.message
              }
            }
          "
        /><datalist id="users">
          <option
            v-for="name in suggestions"
            :key="name"
            :value="name"
          /></datalist
        ><PButton type="submit" label="Réattribuer" :disabled="busy" />
      </form>
      <section>
        <h2>Commentaires</h2>
        <article v-for="entry in comments" :key="entry.id" class="card">
          <strong>{{ entry.auteur }}</strong> · {{ entry.date }}
          <p class="prose">{{ entry.commentaire }}</p>
          <PButton
            v-if="session.is_admin || entry.auteur === session.user.name"
            class="danger"
            label="Supprimer le commentaire"
            :disabled="busy"
            @click="
              () => {
                if (window.confirm('Supprimer ce commentaire ?'))
                  action(`/comments/${entry.id}`, 'DELETE')
              }
            "
          />
        </article>
        <form
          @submit.prevent="
            async () => {
              await action('/comments', 'POST', { commentaire: comment })
              if (!error) comment = ''
            }
          "
        >
          <label
            >Votre commentaire<textarea
              v-model="comment"
              required
              maxlength="100000"
            /></label
          ><PButton type="submit" label="Publier" :disabled="busy" />
        </form>
      </section>
    </template>
  </template>
</template>
