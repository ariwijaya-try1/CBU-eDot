<script setup>
import { useRouter, useRoute } from "vue-router"
import { Offcanvas } from "bootstrap"
import { watch, nextTick } from "vue"

const router = useRouter()
const route = useRoute()

const closeSidebar = () => {
    const sidebar = document.getElementById("sidebarMenu")

    if (!sidebar) return

    const instance = Offcanvas.getOrCreateInstance(sidebar)
    instance.hide()

    document
        .querySelectorAll(".offcanvas-backdrop")
        .forEach(el => el.remove())

    document.body.classList.remove("offcanvas-open")
    document.body.style.overflow = ""
    document.body.style.paddingRight = ""
}

const navigate = async (path) => {
    closeSidebar()

    await nextTick()

    router.push(path)
}

const logout = async () => {

    localStorage.removeItem("token")
    localStorage.removeItem("user")

    closeSidebar()

    await nextTick()

    router.replace("/login")
}

watch(
    () => route.path,
    () => {
        closeSidebar()
    }
)
</script>

<template>

<div
    class="offcanvas offcanvas-start"
    tabindex="-1"
    id="sidebarMenu"
>

    <div class="offcanvas-header">

        <h5 class="fw-bold text-primary">
            CBU-eDot
        </h5>

        <button
            class="btn-close"
            data-bs-dismiss="offcanvas"
        ></button>

    </div>

    <div class="offcanvas-body">

        <button
            class="menu-item"
            @click="navigate('/customer')"
        >
            <i class="bi bi-people-fill me-2"></i>
            Customer Dashboard
        </button>

        <button
            class="menu-item"
            @click="navigate('/products')"
        >
            <i class="bi bi-box-seam me-2"></i>
            Products Dashboard
        </button>

        <hr>

        <button
            class="menu-item logout"
            @click="logout"
        >
            <i class="bi bi-box-arrow-right me-2"></i>
            Logout
        </button>

    </div>

</div>

</template>

<style scoped>

.menu-item{
    width:100%;
    border:none;
    background:transparent;
    text-align:left;
    padding:12px 16px;
    border-radius:10px;
    margin-bottom:8px;
    transition:.2s;
}

.menu-item:hover{
    background:#0d6efd;
    color:white;
}

.logout{
    color:#dc3545;
}

.logout:hover{
    background:#dc3545;
    color:white;
}

</style>