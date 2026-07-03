<script setup>
    import { useRouter } from "vue-router"
    import { Offcanvas } from "bootstrap"

    const router = useRouter()

    const navigate = async (path) => {

    const sidebar = document.getElementById("sidebarMenu")
    const instance = Offcanvas.getOrCreateInstance(sidebar)
    instance.hide()

    setTimeout(async () => {

        await router.push(path)

        document.body.style.overflow = ""
        document.body.style.paddingRight = ""

        document
            .querySelectorAll(".offcanvas-backdrop")
            .forEach(el => el.remove())

    }, 250)

}
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
        type="button"
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
    border-radius:12px;
    margin-bottom:8px;
    transition:.2s;
}

.menu-item:hover{
    background:#0d6efd;
    color:white;
}

</style>