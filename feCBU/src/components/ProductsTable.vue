<script setup>
defineProps({
  products: {
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
                        <th>Product Name</th>
                        <th>Category</th>
                        <th>SKU</th>
                        <th>Price</th>
                        <th>Stock</th>
                    </tr>
                </thead>

                <tbody>
                    <tr v-if="products.length === 0">
                        <td colspan="6" class="text-center text-muted">
                            No product data.
                        </td>
                    </tr>

                    <tr
                        v-for="(product, index) in products"
                        :key="product.id"
                    >
                        <td>{{ index + 1 }}</td>
                        <td>{{ product.name || "-" }}</td>
                        <td>
                            {{ product.categ_id ? product.categ_id[1] : "-" }}
                        </td>

                        <td>
                            {{ product.default_code || "-" }}
                        </td>

                        <td>
                            Rp {{ product.list_price ?? 0 }}
                        </td>

                        <td>
                            {{ product.qty_available ?? 0 }}
                        </td>
                    </tr>
                </tbody>
            </table>
        </div>
    </div>

</template>