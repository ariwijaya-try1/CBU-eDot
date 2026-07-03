<script setup>
</script>

<template>
  <nav class="navbar navbar-expand-lg bg-white border-bottom shadow-sm px-4 py-2">

    <div class="container-fluid">

      <div class="d-flex align-items-center">

        <!-- Hamburger -->
        <button
          class="btn btn-light border me-3"
          type="button"
          data-bs-toggle="offcanvas"
          data-bs-target="#sidebarMenu"
        >
          <i class="bi bi-list fs-4"></i>
        </button>

        <!-- Logo -->
        <div>
          <h5 class="mb-0 fw-bold text-primary">
            CBU-eDot
          </h5>

          <small class="text-muted">
            ERP Dashboard
          </small>

        </div>

      </div>

    </div>

  </nav>
</template>

<style scoped>

.navbar{
    min-height:72px;
}

.btn-light{
    width:48px;
    height:48px;
    border-radius:12px;
}

</style>