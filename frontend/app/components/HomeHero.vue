<script setup>
// Bannière de la page d'accueil, aussi utilisée pour les aperçus de l'administration (même hauteur).
defineProps({
  firstName: { type: String, default: '' },
  image: { type: String, default: '' },
  position: { type: Number, default: 50 },
})
</script>
<template>
  <section
    class="hero"
    :class="{ 'hero--image': image }"
    :style="
      image
        ? {
            backgroundImage: `url(${image})`,
            backgroundPosition: `center ${position}%`,
          }
        : {}
    "
  >
    <p class="eyebrow">Parc national des Cévennes</p>
    <h1>Bonjour {{ firstName }}, que préparez-vous aujourd’hui ?</h1>
    <p>
      Toute la malle de l’équipe est là : déroulés, photos, sons et idées à
      piocher.
    </p>
  </section>
</template>
