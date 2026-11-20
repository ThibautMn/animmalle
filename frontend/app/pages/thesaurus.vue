<script setup>
// Ancienne adresse : le thésaurus est désormais un onglet de l'administration.
await navigateTo({ path: '/administration', query: { onglet: 'thesaurus' } }, { replace: true })
</script>
<template><div /></template>
