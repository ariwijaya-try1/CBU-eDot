import axios from 'axios'
import router from '../router'
import { useApiKey } from '../composables/useApiKey'

// Same origin dengan bridge (UI disajikan di /ui/), jadi path API cukup absolut: '/api/...'
const http = axios.create({ timeout: 60000 })

http.interceptors.request.use((config) => {
  const { apiKey } = useApiKey()
  if (apiKey.value && !config.headers['x-api-key']) {
    config.headers['x-api-key'] = apiKey.value
  }
  return config
})

http.interceptors.response.use(
  (res) => res,
  (err) => {
    // 401 = API key salah/hilang -> kembali ke login (kecuali sedang di login)
    if (err.response?.status === 401 && router.currentRoute.value.name !== 'login') {
      useApiKey().clearApiKey()
      router.push({ name: 'login' })
    }
    return Promise.reject(err)
  },
)

export default http
