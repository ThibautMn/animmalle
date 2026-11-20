<script setup>
import { useSessionStore } from '~/stores/session'
const session = useSessionStore()
const route = useRoute()
// Le thésaurus relève du groupe thésaurus ; utilisateurs et bannières, des administrateurs.
const tabs = computed(() =>
  [
    { id: 'thesaurus', label: 'Thésaurus', allowed: session.can_edit_thesaurus },
    { id: 'utilisateurs', label: 'Utilisateurs', allowed: session.is_admin },
    { id: 'banniere', label: 'Bannière', allowed: session.is_admin },
  ].filter((tab) => tab.allowed),
)
const current = computed(
  () => tabs.value.find((tab) => tab.id === route.query.onglet) || tabs.value[0],
)
</script>
<template>
  <h1>Administration</h1>
  <p v-if="!tabs.length" role="alert">
    Cette page est réservée aux administrateurs.
  </p>
  <template v-else>
    <nav class="admin-tabs" aria-label="Sections de l’administration">
      <NuxtLink
        v-for="tab in tabs"
        :key="tab.id"
        :to="{ path: '/administration', query: { onglet: tab.id } }"
        :class="{ active: current.id === tab.id }"
        >{{ tab.label }}</NuxtLink
      >
    </nav>
    <AdminThesaurus v-if="current.id === 'thesaurus'" />
    <p v-else-if="current.id === 'utilisateurs'" class="muted">
      La gestion des utilisateurs sera ajoutée prochainement.
    </p>
    <AdminBanners v-else />
  </template>
</template>
