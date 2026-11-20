<script setup>
import { useSessionStore } from '~/stores/session'
const session = useSessionStore()
const api = useApi()
const firstName = computed(() => (session.user?.name || '').split(' ')[0])
const statuts = { 1: 'Validée', 2: 'À valider', 3: 'Brouillon' }
const home = ref(null)
const error = ref('')
const formatDate = (value) =>
  value ? new Date(value).toLocaleDateString('fr-FR') : ''
const excerpt = (text) => {
  const plain = String(text || '').replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim()
  return plain.length > 140 ? `${plain.slice(0, 140)}…` : plain
}
onMounted(async () => {
  try {
    home.value = await api('/home')
  } catch {
    error.value = 'Impossible de charger les nouveautés.'
  }
})
</script>
<template>
  <section class="hero">
    <p class="eyebrow">Parc national des Cévennes</p>
    <h1>Bonjour {{ firstName }}, que préparez-vous aujourd’hui ?</h1>
    <p>
      Toute la malle de l’équipe est là : déroulés, photos, sons et idées à
      piocher.
    </p>
  </section>
  <div class="home-actions">
    <NuxtLink class="button" to="/animations">Parcourir la pédathèque</NuxtLink>
    <NuxtLink class="button secondary" to="/animations/nouveau"
      >Créer une animation</NuxtLink
    >
  </div>
  <p v-if="error" class="error" role="alert">{{ error }}</p>
  <div v-else-if="home" class="home-panels">
    <section
      class="home-panel home-panel--wide"
      aria-labelledby="home-latest"
    >
      <h2 id="home-latest" class="section-title">La dernière animation</h2>
      <p v-if="!home.latest" class="muted">Aucune animation.</p>
      <div v-else class="home-latest">
        <NuxtLink :to="`/animations/${home.latest.id}`">{{
          home.latest.titre
        }}</NuxtLink>
        <small
          >{{ home.latest.auteurs }} ·
          {{ formatDate(home.latest.date_modif) }}</small
        >
        <span>{{ excerpt(home.latest.description) }}</span>
      </div>
    </section>
    <section class="home-panel" aria-labelledby="home-comments">
      <h2 id="home-comments" class="section-title">Derniers commentaires</h2>
      <p v-if="!home.comments.length" class="muted">Aucun commentaire.</p>
      <ul v-else class="home-list">
        <li v-for="item in home.comments" :key="item.id">
          <NuxtLink :to="`/animations/${item.animation_id}`">{{
            item.animation_titre
          }}</NuxtLink>
          <small>{{ item.auteur }} · {{ formatDate(item.date) }}</small>
          <span>{{ excerpt(item.commentaire) }}</span>
        </li>
      </ul>
    </section>
    <section
      v-if="home.to_validate"
      class="home-panel home-panel--alert"
      aria-labelledby="home-validate"
    >
      <h2 id="home-validate" class="section-title">
        Animations à valider
        <span class="home-count">{{ home.to_validate.length }}</span>
      </h2>
      <p v-if="!home.to_validate.length" class="muted">
        Aucune animation en attente.
      </p>
      <ul v-else class="home-list">
        <li v-for="item in home.to_validate" :key="item.id">
          <NuxtLink :to="`/animations/${item.id}`">{{ item.titre }}</NuxtLink>
        </li>
      </ul>
    </section>
    <section v-else class="home-panel" aria-labelledby="home-mine">
      <h2 id="home-mine" class="section-title">Mes animations</h2>
      <p v-if="!home.mine?.length" class="muted">
        Vous n’avez pas encore créé d’animation.
      </p>
      <ul v-else class="home-list">
        <li v-for="item in home.mine" :key="item.id">
          <NuxtLink :to="`/animations/${item.id}`">{{ item.titre }}</NuxtLink>
          <small>{{ statuts[item.statut] }}</small>
        </li>
      </ul>
    </section>
  </div>
</template>
