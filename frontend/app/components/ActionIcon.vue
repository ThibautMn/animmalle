<script setup>
defineProps({ name: String })
const paths = {
  preview:
    'M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12m10-3a3 3 0 1 0 0 6 3 3 0 0 0 0-6',
  download: 'M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5',
  zip: 'M4 3h16v18H4zM12 3v3m0 3v3m0 3v3M10 6h4m-4 6h4',
  edit: 'm15 4 5 5M4 20l5-1L21 7l-5-5L4 14z',
  image: 'M3 5h18v14H3zM3 16l5-5 4 4 3-3 6 6M16 9.5h.01',
  print: 'M7 9V3h10v6M7 17H4v-7h16v7h-3M7 14h10v7H7z',
  more: 'M5 12h.01M12 12h.01M19 12h.01',
  add: 'M12 5v14M5 12h14',
  check: 'M4 12l5 5L20 6',
  close: 'M6 6l12 12M18 6 6 18',
  up: 'm6 15 6-6 6 6',
  down: 'm6 9 6 6 6-6',
  delete: 'M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7m4-7v7',
}
</script>
<template>
  <svg
    viewBox="0 0 24 24"
    width="20"
    height="20"
    fill="none"
    stroke="currentColor"
    stroke-width="1.7"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <path :d="paths[name]" />
  </svg>
</template>
