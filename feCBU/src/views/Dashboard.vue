<script setup>
import { ref, onMounted, watch } from "vue"
import api from "../services/api"
import Navbar from "../components/Navbar.vue"
import SearchBar from "../components/SearchBar.vue"
import CustomerTable from "../components/CustomerTable.vue"
import "bootstrap-icons/font/bootstrap-icons.css"

const customers = ref([])
const page = ref(1)
const limit = ref(10)
const loading = ref(false)
const error = ref("")
const keyword = ref("")
const getCustomers = async () => {
    loading.value = true
    error.value = ""
    try {
        console.log("Page : ", page.value)
        console.log("Limit : ", limit.value)
        const response = await api.get("/api/customers", {
            params: {
            page: page.value,
            limit: limit.value
            }
        })
        console.log(response.data)
        customers.value = response.data.data
    } catch (err) {
        console.error(err)
        error.value = "Failed to load customers."
    } finally {
        loading.value = false
    }
}

const searchCustomers = async () => {

    console.log("SEARCH DIPANGGIL")
    console.log("Keyword:", keyword.value)

    if (!keyword.value.trim()) {
        getCustomers()
        return
    }

    try {

        const response = await api.get("/api/customers/search", {
            params: {
                keyword: keyword.value
            }
        })

        console.log("SEARCH RESPONSE:", response.data)

        customers.value = response.data.data

    } catch (err) {

        console.error(err)

    }

}

    onMounted(() => {
        getCustomers()
    })

watch(limit, () => {
    page.value=1
    getCustomers()
    watch(keyword, (newValue) => {
        console.log("WATCH:", newValue)
        searchCustomers()
    })
})
</script>

<!-- Tampilan dari Dashboard -->
<template>
    <Navbar />
    <div class="style-wrapper">
        <div class="container mt-4">
            <h2 class="fw-bold">
                Customer Dashboard
            </h2>

            <p class="text-muted">
                Manage customer information from Odoo ERP
            </p>

    <SearchBar
        v-model="keyword"
    />

    <!-- Limitasi baris -->
    <div class="d-flex align-items-center justify-content-between mt-3">

    <div class="d-flex align-items-center">

        <label class="me-2">

            Show

        </label>

        <select
            class="form-select w-auto"
            v-model="limit"
        >

            <option :value="10">10</option>

            <option :value="25">25</option>

            <option :value="50">50</option>

        </select>

        <label class="ms-2">

            entries

        </label>

    </div>

</div>

    <CustomerTable
        :customers="customers"
    />
        </div>
    </div>
</template>

<!-- Settingan design -->
<style scoped>
    .style-wrapper{
        background:#f8fafc;
        min-height:100vh;
    }
</style>