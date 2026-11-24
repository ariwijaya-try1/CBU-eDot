import { createRouter, createWebHashHistory } from 'vue-router'
import { useApiKey } from '../composables/useApiKey'

// Hash history (/ui/#/...) -> refresh halaman tidak butuh SPA fallback di FastAPI
const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/login', name: 'login', component: () => import('../views/LoginView.vue'), meta: { public: true } },
    { path: '/', name: 'dashboard', component: () => import('../views/DashboardView.vue') },
    { path: '/:pathMatch(.*)*', redirect: { name: 'dashboard' } },
  ],
})

router.beforeEach((to) => {
  const { hasApiKey } = useApiKey()
  if (!to.meta.public && !hasApiKey.value) return { name: 'login' }
  if (to.name === 'login' && hasApiKey.value) return { name: 'dashboard' }
})

export default router
