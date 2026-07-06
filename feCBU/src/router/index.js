import { createRouter, createWebHistory } from "vue-router"

import AuthLayout from "../layouts/AuthLayout.vue"
import DashboardLayout from "../layouts/DashboardLayout.vue"

import Login from "../views/Auth/Login.vue"
import Register from "../views/Auth/Register.vue"

import CustomerDashboard from "../views/Dashboard/CustomerDashboard.vue"
import ProductsDashboard from "../views/Dashboard/ProductsDashboard.vue"

const router = createRouter({
  history: createWebHistory(),

  routes: [

    {
      path: "/",
      component: AuthLayout,
      children: [
        {
          path: "",
          redirect: "/register",
        },
        {
          path: "register",
          name: "Register",
          component: Register,
        },
        {
          path: "login",
          name: "Login",
          component: Login,
        },
      ],
    },

    {
      path: "/",
      component: DashboardLayout,
      children: [
        {
          path: "customer",
          name: "Customer",
          component: CustomerDashboard,
        },
        {
          path: "products",
          name: "Products",
          component: ProductsDashboard,
        },
      ],
    },

  ],
})

export default router