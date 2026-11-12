<script setup>
import { useSessionStore } from '~/stores/session'
const session = useSessionStore()
const api = useApi()
const route = useRoute()
const error = ref('')
const busy = ref(true)
const login = ref('')
const password = ref('')
async function connect() {
  busy.value = true
  error.value = ''
  try {
    if (!session.csrf_token) session.apply(await api('/auth/session'))
    session.apply(
      await api('/auth/login', {
        method: 'POST',
        body: { login: login.value, password: password.value }
      })
    )
    password.value = ''
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}
async function logout() {
  error.value = ''
  try {
    await api('/auth/logout', { method: 'POST' })
    session.clear()
    await navigateTo('/')
  } catch (e) {
    error.value = e.message
  }
}
onMounted(() => {
  const el = document.querySelector('body header')
  if (!el || typeof ResizeObserver === 'undefined') return
  new ResizeObserver(() => {
    document.documentElement.style.setProperty(
      '--site-h',
      `${el.offsetHeight}px`
    )
  }).observe(el)
})
onMounted(async () => {
  try {
    session.apply(await api('/auth/session'))
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
})
</script>
<template>
  <a class="skip" href="#content">Aller au contenu</a>
  <header>
    <NuxtLink class="brand" to="/"
      ><span
        >Anim’Malle <small>Parc national des Cévennes</small></span
      ></NuxtLink
    >
    <nav v-if="session.user" class="topnav" aria-label="Navigation principale">
      <NuxtLink to="/">Accueil</NuxtLink>
      <NuxtLink to="/animations">Pédathèque</NuxtLink>
      <NuxtLink to="/materials">Médiathèque</NuxtLink>
      <NuxtLink to="/outils">Outils facilitateurs</NuxtLink>
      <NuxtLink to="/stats">Statistiques</NuxtLink>
      <NuxtLink v-if="session.can_edit_thesaurus" to="/thesaurus">Thésaurus</NuxtLink>
    </nav>
    <div v-if="session.user" class="userbox">
      <span class="avatar" aria-hidden="true">{{ initials }}</span>
      <span class="name">{{ firstName }}</span>
      <PButton class="linkbtn" label="Se déconnecter" @click="logout" />
    </div>
  </header>
  <main id="content">
    <p v-if="error" role="alert" class="error">{{ error }}</p>
    <p v-if="busy" role="status">Chargement de la session…</p>
    <section v-else-if="!session.user" class="login card">
      <p class="eyebrow">Bienvenue dans la malle pédagogique</p>
      <h1>Content de vous revoir.</h1>
      <p class="muted">
        Connectez-vous pour consulter et enrichir les ressources de l’équipe.
      </p>
      <form @submit.prevent="connect">
        <label
          >Identifiant<input
            v-model="login"
            autocomplete="username"
            required /></label
        ><label
          >Mot de passe<input
            v-model="password"
            type="password"
            autocomplete="current-password"
            required /></label
        ><PButton type="submit" label="Se connecter" :disabled="busy" />
      </form>
    </section>
    <NuxtPage v-else :key="route.path" />
  </main>
  <footer>
    <span>Anim’Malle · Les ressources pédagogiques des Cévennes</span
    ><span>Bonne animation !</span>
  </footer>
</template>
