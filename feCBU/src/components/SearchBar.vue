<script setup>
    const model = defineModel()
</script>

<template>
    <div class="card shadow-sm mt-4">
        <div class="card-body">
            <label class="form-label fw-semibold">
                Search Customer
            </label>

            <input
                class="form-control"
                placeholder="Search..."
                v-model="model"
            >
        </div>
    </div>
</template>