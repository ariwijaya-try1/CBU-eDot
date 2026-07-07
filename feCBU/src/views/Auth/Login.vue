<script setup>
    import { ref } from "vue"
    import api from "../../services/api"
    import { useRouter } from "vue-router"

    const email = ref("")
    const password = ref("")
    const router = useRouter()
    
    const login = async () => {
        try {
            const response = await api.post("/login", {
                email: email.value,
                password: password.value
            })
            console.log(response.data)
            router.push("/customer")
        } catch (error) {
            console.log(error.response?.data || error.message)
        }
    }
</script>

<template>
    <div class="position-fixed top-0 start-0 w-100 h-100 bg-light d-flex align-items-center justify-content-center p-4">
        <Transition name="popup" appear>
            <div class="w-100 bg-white rounded-4 shadow overflow-hidden" style="max-width: 400px;">
                <div class="bg-primary py-3 d-flex justify-content-center align-items-center text-white font-weight-bold fs-1 tracking-tight user-select-none">
                    CBU
                    <div class="d-inline-flex align-items-center justify-content-center border border-3 border-white rounded-circle mx-1 text-lowercase" style="width: 40px; height: 40px;">
                        <span class="fs-2 lh-1" style="margin-top: -4px;">e</span>
                    </div>
                    -dot
                </div>

                <div class="p-4 text-center">
                    <h1 class="text-dark fw-bold m-2 display-6">
                        Login
                    </h1>

                    <p class="text-muted mb-4">
                        Log in to your account
                    </p>

                    <form @submit.prevent="login" class="d-flex flex-column gap-3">
                        <div class="input-group">
                            <span class="input-group-text bg-light text-secondary border-end-0 rounded-start-3">
                                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" style="width: 24px; height: 24px;">
                                    <path stroke-linecap="round" stroke-linejoin="round" d="M15.75 6a3.75 3.75 0 1 1-7.5 0 3.75 3.75 0 0 1 7.5 0ZM4.501 20.118a7.5 7.5 0 0 1 14.998 0A17.933 17.933 0 0 1 12 21.75c-2.676 0-5.216-.584-7.499-1.632Z" />
                                </svg>
                            </span>
                            <input
                                v-model="email"
                                type="email"
                                placeholder="Email"
                                class="form-control bg-light border-start-0 rounded-end-3 py-2 fs-5"
                                required
                            >
                        </div> 

                        <div class="input-group">
                            <span class="input-group-text bg-light text-secondary border-end-0 rounded-start-3">
                                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" style="width: 24px; height: 24px;">
                                    <path stroke-linecap="round" stroke-linejoin="round" d="M15.75 5.25a3 3 0 0 1 3 3m3 0a6 6 0 0 1-7.029 5.912c-.563-.097-1.159.026-1.563.43L10.5 17.25H8.25v2.25H6v2.25H2.25v-2.818c0-.597.237-1.17.659-1.591l6.499-6.499c.404-.404.527-1 .43-1.563A6 6 0 1 1 21.75 8.25Z" />
                                </svg>
                            </span>
                            <input
                                v-model="password"
                                type="password"
                                placeholder="Password"
                                class="form-control bg-light border-start-0 rounded-end-3 py-2 fs-5"
                                required
                            >
                        </div> 

                        <button type="submit" class="btn btn-primary w-100 rounded-3 py-2 fw-semibold mt-2 fs-5">
                            Login
                        </button>
                    </form> 

                    <p class="mt-4 mb-2 text-center text-muted">
                        Don’t have an account?
                        <RouterLink to="/register" class="fw-bold text-primary text-decoration-none ms-1 link-underline-hover">Register here</RouterLink>
                    </p>

                </div>
            </div>
        </Transition>
    </div>
</template> 

<style scoped>
    /* Mengatur fokus agar border input-group tidak berantakan saat diklik */
    .form-control:focus {
        box-shadow: none;
        border-color: #dee2e6;
    }
    .input-group:focus-within .input-group-text,
    .input-group:focus-within .form-control {
        border-color: #0d6efd;
        background-color: #fff !important;
    }

    .link-underline-hover:hover {
        text-decoration: underline !important;
    }

    /* Animasi Transisi */
    .popup-enter-active {
        transition: all .35s ease;
    }

    .popup-enter-from {
        opacity: 0;
        transform: translateY(20px) scale(.96);
    }

    .popup-enter-to {
        opacity: 1;
        transform: translateY(0) scale(1);
    }
</style>