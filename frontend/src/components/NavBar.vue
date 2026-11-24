<script setup>
import { useRouter } from 'vue-router'
import { useApiKey } from '../composables/useApiKey'
import logoUrl from '../assets/logo.png'

const router = useRouter()
const { clearApiKey } = useApiKey()

function logout() {
  clearApiKey()
  router.push({ name: 'login' })
}
</script>

<template>
  <nav class="navbar navbar-expand-lg navbar-dark brand-navbar px-3 px-lg-5 py-2 shadow-sm sticky-top">
    <div class="container-fluid p-0">
      <RouterLink class="navbar-brand d-flex align-items-center gap-2 m-0" :to="{ name: 'dashboard' }">
        <img :src="logoUrl" alt="CBU" width="30" height="30" />
        <span class="fw-bold fs-4">Edot Bridge</span>
      </RouterLink>

      <button
        class="navbar-toggler border-0 shadow-none"
        type="button"
        data-bs-toggle="collapse"
        data-bs-target="#mainNavbar"
        aria-label="Menu"
      >
        <i class="bi bi-list fs-1 text-white"></i>
      </button>

      <div id="mainNavbar" class="collapse navbar-collapse mt-3 mt-lg-0">
        <ul class="navbar-nav ms-auto me-lg-4 gap-lg-3 align-items-lg-center">
          <li class="nav-item">
            <RouterLink class="nav-link fw-semibold" :to="{ name: 'dashboard' }">
              <i class="bi bi-speedometer2 me-1"></i>Dashboard
            </RouterLink>
          </li>
          <li class="nav-item">
            <a class="nav-link fw-semibold" href="/docs" target="_blank" rel="noopener">
              <i class="bi bi-box-arrow-up-right me-1"></i>Swagger
            </a>
          </li>
        </ul>
        <button class="btn btn-sm btn-outline-light fw-semibold px-3" @click="logout">
          <i class="bi bi-box-arrow-right me-1"></i>Keluar
        </button>
      </div>
    </div>
  </nav>
</template>

<style scoped>
.brand-navbar {
  background-color: var(--brand);
}

.brand-navbar .nav-link {
  color: #fff;
}

.brand-navbar .nav-link:hover,
.brand-navbar .nav-link.router-link-exact-active {
  color: #fff;
  opacity: 0.85;
}
</style>
