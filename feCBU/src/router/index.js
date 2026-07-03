import { createRouter, createWebHistory } from "vue-router"

import CustomerDashboard from "../views/CustomerDashboard.vue"
import ProductsDashboard from "../views/ProductsDashboard.vue"

const routes = [
    {
        path: "/",
        redirect: "/customer"
    },
    {
        path: "/customer",
        component: CustomerDashboard
    },
    {
        path: "/products",
        component: ProductsDashboard
    }
]

const router = createRouter({
    history: createWebHistory(),
    routes
})

export default router