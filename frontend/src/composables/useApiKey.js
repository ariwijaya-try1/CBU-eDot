import { ref, computed } from 'vue'

// API key bridge disimpan di localStorage (sama seperti Swagger persistAuthorization).
// Aman selama bridge hanya dibuka dari 127.0.0.1. try/catch: storage bisa diblokir browser.
const STORAGE_KEY = 'edot_bridge_api_key'

function readStored() {
  try {
    return localStorage.getItem(STORAGE_KEY) || ''
  } catch {
    return ''
  }
}

// State modul-level -> satu sumber untuk semua komponen
const apiKey = ref(readStored())

export function useApiKey() {
  function setApiKey(value) {
    apiKey.value = value
    try {
      localStorage.setItem(STORAGE_KEY, value)
    } catch {
      /* storage tidak tersedia: key cuma hidup selama tab terbuka */
    }
  }

  function clearApiKey() {
    apiKey.value = ''
    try {
      localStorage.removeItem(STORAGE_KEY)
    } catch {
      /* abaikan */
    }
  }

  return {
    apiKey,
    hasApiKey: computed(() => apiKey.value !== ''),
    setApiKey,
    clearApiKey,
  }
}
