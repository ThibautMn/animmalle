<script setup>
defineProps({
  kind: { type: String, default: 'file' },
  size: { type: Number, default: 48 }
})
// Tracés 24×24 : note de musique, diaporama, document, feuille de calcul, archive, fichier générique.
const paths = {
  audio: 'M9 18V5l12-2v13M9 18a3 3 0 1 1-6 0 3 3 0 0 1 6 0m12-2a3 3 0 1 1-6 0 3 3 0 0 1 6 0',
  presentation: 'M3 4h18v12H3zM12 16v4m-4 0h8M8 12V9m4 3V7m4 5v-2',
  document: 'M6 2h9l5 5v15H6zM14 2v6h6M9 13h8M9 17h8M9 9h3',
  spreadsheet: 'M5 3h14v18H5zM5 9h14M5 15h14M12 9v12',
  archive: 'M4 3h16v18H4zM12 3v3m0 3v3m0 3v3M10 6h4m-4 6h4',
  pdf: 'M6 2h9l5 5v15H6zM14 2v6h6M9 14h6M9 18h6',
  video: 'M3 5h18v14H3zM10 9l5 3-5 3z',
  image: 'M3 5h18v14H3zM3 16l5-5 4 4 3-3 6 6M16 9.5h.01',
  file: 'M6 2h9l5 5v15H6zM14 2v6h6'
}
</script>
<template>
  <svg
    viewBox="0 0 24 24"
    :width="size"
    :height="size"
    fill="none"
    stroke="currentColor"
    stroke-width="1.5"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <path :d="paths[kind] || paths.file" />
  </svg>
</template>
