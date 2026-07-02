<script setup>
defineProps({
  customers: {
    type: Array,
    default: () => []
  }
})
</script>

<template>

<div class="card shadow-sm mt-4">
    <div class="card-body">
        <table class="table table-hover">
            <thead>
                <tr>
                    <th>No</th>
                    <th>Name</th>
                    <th>Email</th>
                    <th>Phone</th>
                </tr>

            </thead>

            <tbody>

                <tr v-if="customers.length === 0">
                    <td colspan="4" class="text-center text-muted">
                        No customer data.
                    </td>
                </tr>

                <tr
                    v-for="(customer, index) in customers"
                    :key="customer.id"
                >
                    <td>{{ index + 1 }}</td>
                    <td>{{ customer.name }}</td>
                    <td>{{ customer.email }}</td>
                    <td>{{ customer.phone }}</td>
                </tr>

            </tbody>

        </table>

    </div>

</div>

</template>