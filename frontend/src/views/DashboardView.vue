<script setup>
import { ref, computed, onMounted } from 'vue'
import { checkBridge, getOpenApi } from '../services/bridgeService'

const loading = ref(true)
const bridgeOk = ref(false)
const errorMessage = ref('')
const appTitle = ref('')
const groups = ref([]) // [{ tag, count }]

const METHODS = ['get', 'post', 'put', 'patch', 'delete']

// Hitung endpoint per grup Swagger (tag pertama) dari openapi.json
function countByTag(spec) {
  const counts = {}
  for (const ops of Object.values(spec.paths || {})) {
    for (const method of METHODS) {
      if (!ops[method]) continue
      const tag = ops[method].tags?.[0] || 'default'
      counts[tag] = (counts[tag] || 0) + 1
    }
  }
  return Object.entries(counts)
    .map(([tag, count]) => ({ tag, count }))
    .sort((a, b) => b.count - a.count)
}

const totalEndpoints = computed(() => groups.value.reduce((sum, g) => sum + g.count, 0))

async function load() {
  loading.value = true
  errorMessage.value = ''
  try {
    const [health, spec] = await Promise.all([checkBridge(), getOpenApi()])
    bridgeOk.value = health?.status === 'ok'
    appTitle.value = spec.info?.title || ''
    groups.value = countByTag(spec)
  } catch (err) {
    bridgeOk.value = false
    if (err.response?.status !== 401) {
      errorMessage.value = 'Gagal memuat data dari bridge.'
    }
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div>
    <div class="page-hero py-4 py-lg-5 mb-4">
      <div class="container">
        <h1 class="mb-2">Edot <span class="text-brand">Bridge</span></h1>
        <p class="text-muted mb-0">Panel operasional integrasi Odoo &rarr; eSuite</p>
      </div>
    </div>

    <div class="container pb-4">
      <div v-if="errorMessage" class="alert alert-danger d-flex justify-content-between align-items-center">
        <span><i class="bi bi-exclamation-triangle-fill me-2"></i>{{ errorMessage }}</span>
        <button class="btn btn-sm btn-outline-danger" @click="load">Coba lagi</button>
      </div>

      <div class="row g-3 mb-4">
        <div class="col-md-4">
          <div class="stat-card h-100 p-3 d-flex align-items-center gap-3">
            <div class="icon-tile"><i class="bi bi-activity"></i></div>
            <div>
              <div class="text-muted small fw-medium">Status Bridge</div>
              <div v-if="loading" class="fw-bold text-muted">Memeriksa...</div>
              <div v-else-if="bridgeOk" class="fw-bold text-success">
                <i class="bi bi-check-circle-fill me-1"></i>Terhubung
              </div>
              <div v-else class="fw-bold text-danger">
                <i class="bi bi-x-circle-fill me-1"></i>Tidak terhubung
              </div>
            </div>
          </div>
        </div>
        <div class="col-md-4">
          <div class="stat-card h-100 p-3 d-flex align-items-center gap-3">
            <div class="icon-tile"><i class="bi bi-diagram-3"></i></div>
            <div>
              <div class="text-muted small fw-medium">Total Endpoint</div>
              <div class="fw-bold fs-4 text-brand">{{ loading ? '-' : totalEndpoints }}</div>
            </div>
          </div>
        </div>
        <div class="col-md-4">
          <div class="stat-card h-100 p-3 d-flex align-items-center gap-3">
            <div class="icon-tile"><i class="bi bi-hdd-network"></i></div>
            <div class="text-truncate">
              <div class="text-muted small fw-medium">Aplikasi</div>
              <div class="fw-bold text-truncate">{{ appTitle || '-' }}</div>
            </div>
          </div>
        </div>
      </div>

      <div class="card-brand">
        <div class="card-header d-flex justify-content-between align-items-center">
          <span><i class="bi bi-grid-1x2-fill text-brand me-2"></i>Endpoint per Grup</span>
          <a href="/docs" target="_blank" rel="noopener" class="small fw-semibold text-decoration-none">
            Buka Swagger &rarr;
          </a>
        </div>
        <div v-if="loading" class="p-4 text-muted small">Memuat...</div>
        <div v-else-if="groups.length === 0" class="p-4 text-muted small">Belum ada data.</div>
        <div v-else class="table-responsive">
          <table class="table table-hover table-brand align-middle mb-0">
            <thead>
              <tr>
                <th>Grup</th>
                <th class="text-end" style="width: 140px">Jumlah</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="g in groups" :key="g.tag">
                <td class="fw-semibold">{{ g.tag }}</td>
                <td class="text-end">{{ g.count }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>
