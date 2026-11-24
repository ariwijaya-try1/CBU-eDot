<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useApiKey } from '../composables/useApiKey'
import { checkBridge } from '../services/bridgeService'
import logoUrl from '../assets/logo.png'

const router = useRouter()
const { setApiKey } = useApiKey()

const keyInput = ref('')
const showKey = ref(false)
const errorMessage = ref('')
const isSubmitting = ref(false)

async function handleSubmit() {
  errorMessage.value = ''
  isSubmitting.value = true
  const key = keyInput.value.trim()
  try {
    // Validasi ke bridge dulu (GET / kena verify_api_key) sebelum key disimpan
    await checkBridge(key)
    setApiKey(key)
    router.push({ name: 'dashboard' })
  } catch (err) {
    if (err.response?.status === 401) {
      errorMessage.value = 'API key salah.'
    } else if (err.response?.status === 429) {
      errorMessage.value = 'Terlalu banyak percobaan. Tunggu sebentar lalu coba lagi.'
    } else {
      errorMessage.value = 'Bridge tidak bisa dihubungi. Pastikan container berjalan.'
    }
  } finally {
    isSubmitting.value = false
  }
}
</script>

<template>
  <div class="login-wrapper min-vh-100 d-flex align-items-center justify-content-center p-3">
    <Transition name="popup" appear>
      <div class="card border-0 shadow-lg w-100 login-card">
        <div class="login-header text-white py-4 d-flex justify-content-center align-items-center gap-2">
          <img :src="logoUrl" alt="CBU" width="30" height="30" />
          <span class="fw-bold fs-2 user-select-none">Edot Bridge</span>
        </div>

        <div class="card-body p-4">
          <h1 class="fw-bold fs-3 mb-1 text-center">Masuk</h1>
          <p class="text-muted mb-4 text-center">Gunakan API key bridge</p>

          <form @submit.prevent="handleSubmit">
            <div class="input-group mb-3">
              <span class="input-group-text bg-white text-muted"><i class="bi bi-key"></i></span>
              <input
                v-model="keyInput"
                :type="showKey ? 'text' : 'password'"
                class="form-control py-2"
                placeholder="API key"
                autocomplete="current-password"
                required
              />
              <button
                type="button"
                class="btn btn-light border"
                :aria-label="showKey ? 'Sembunyikan' : 'Tampilkan'"
                @click="showKey = !showKey"
              >
                <i :class="showKey ? 'bi bi-eye-slash' : 'bi bi-eye'"></i>
              </button>
            </div>

            <p v-if="errorMessage" class="text-danger small text-center mb-3">{{ errorMessage }}</p>

            <button type="submit" class="btn btn-primary w-100 py-2" :disabled="isSubmitting || !keyInput.trim()">
              {{ isSubmitting ? 'Memeriksa...' : 'Masuk' }}
            </button>
          </form>
        </div>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.login-wrapper {
  background: linear-gradient(135deg, var(--brand-soft-2) 0%, #ffffff 50%, #f1f5f9 100%);
}

.login-card {
  max-width: 380px;
  border-radius: 1.5rem;
  overflow: hidden;
}

.login-header {
  background: var(--brand);
}

.popup-enter-active {
  transition: all 0.35s ease;
}

.popup-enter-from {
  opacity: 0;
  transform: translateY(20px) scale(0.96);
}
</style>
