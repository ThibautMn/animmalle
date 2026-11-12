<script setup>
import { useSessionStore } from '~/stores/session'
const session = useSessionStore()
const firstName = computed(() => (session.user?.name || '').split(' ')[0])
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
  <h2 class="section-title">Par où commencer ?</h2>
  <div class="tiles">
    <NuxtLink class="tile" to="/animations"
      ><b>Pédathèque</b
      ><span>Les animations, séquence après séquence.</span></NuxtLink
    ><NuxtLink class="tile" to="/materials"
      ><b>Médiathèque</b
      ><span>Images, sons, vidéos et supports.</span></NuxtLink
    ><NuxtLink class="tile" to="/outils"
      ><b>Outils facilitateurs</b
      ><span>Des techniques pour accompagner le groupe.</span></NuxtLink
    ><NuxtLink class="tile" to="/stats"
      ><b>Statistiques</b><span>Un aperçu de la malle.</span></NuxtLink
    >
  </div>
</template>
