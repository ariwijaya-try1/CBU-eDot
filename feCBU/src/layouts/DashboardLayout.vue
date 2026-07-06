<script setup>
import Navbar from "../components/Navbar.vue"
import Sidebar from "../components/Sidebar.vue"
</script>

<template>

  <Navbar />

  <Sidebar />

  <main class="container-fluid py-4">
      <RouterView />
  </main>

</template>