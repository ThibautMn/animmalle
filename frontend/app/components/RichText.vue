<script setup>
import { toRichHtml } from '../../lib/richtext.mjs'
// Affiche un texte (brut historique ou HTML nettoyé par le backend).
defineProps({ text: String })
</script>
<template>
  <div class="rich-view" v-html="toRichHtml(text)" />
</template>
