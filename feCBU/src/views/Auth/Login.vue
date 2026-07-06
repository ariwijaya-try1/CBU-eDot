<script setup>
    import { ref } from "vue"
    import api from "../../services/api"
    import { useRouter } from "vue-router"

    const email = ref("")
    const password = ref("")
    const router = useRouter()
    const login = async () => {
            try{
                const response = await api.post("/login",{
                    email: email.value,
                    password: password.value
                })
                console.log(response.data)
                router.push("/customer")
            }catch (error) {
                console.log(error.response?.data || error.message)
            }
    }
</script>

<template>
     <div class="fixed inset-0 w-full h-full bg-gray-100 flex items-center justify-center p-4 py-8">
        <Transition name="popup" appear>
            <div class="w-full max-w-sm bg-white rounded-3xl shadow-2xl overflow-hidden">
                <!-- Header Logo -->
                <div class="bg-[#1A73E8] py-3 flex justify-center items-center">
                    <div class="text-white font-bold text-4xl flex items-center tracking-tight select-none">
                        CBU
                        <div class="inline-flex items-center justify-center border-[3px] border-white rounded-full w-10 h-10 mx-1">
                            <span class="text-3xl leading-none">e</span>
                        </div>
                        -dot
                    </div>
                </div>

                <!-- Body Form -->
                <div class="p-8 py-3 text-center">
                    <!-- Judul Login  -->
                    <h1 class="text-gray-900 text-5xl font-bold m-2">
                        Login
                    </h1>

                    <p class="text-gray-500 m-3">
                        Log in to your account
                    </p>

                    <form @submit.prevent="login" class="mt-4 space-y-4">
                        <!-- Input Email -->
                        <div class="relative">
                            <span class="absolute left-4 text-gray-600">
                                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="w-6 h-6">
                                    <path stroke-linecap="round" stroke-linejoin="round" d="M15.75 6a3.75 3.75 0 1 1-7.5 0 3.75 3.75 0 0 1 7.5 0ZM4.501 20.118a7.5 7.5 0 0 1 14.998 0A17.933 17.933 0 0 1 12 21.75c-2.676 0-5.216-.584-7.499-1.632Z" />
                                </svg>
                            </span>
                            <input
                                v-model="email"
                                type="email"
                                placeholder="Email"
                                class="w-full rounded-xl border border-gray-300 pl-12 pr-4 h-14 text-black placeholder-gray-500 outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 bg-gray-50"
                            >
                        </div> 

                        <!-- Input Password -->
                        <div class="relative">
                            <span class="absolute left-4 text-gray-600">
                                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="w-6 h-6">
                                    <path stroke-linecap="round" stroke-linejoin="round" d="M15.75 5.25a3 3 0 0 1 3 3m3 0a6 6 0 0 1-7.029 5.912c-.563-.097-1.159.026-1.563.43L10.5 17.25H8.25v2.25H6v2.25H2.25v-2.818c0-.597.237-1.17.659-1.591l6.499-6.499c.404-.404.527-1 .43-1.563A6 6 0 1 1 21.75 8.25Z" />
                                </svg>
                            </span>
                            <input
                                v-model="password"
                                type="password"
                                placeholder="Password"
                                class="w-full rounded-xl border border-gray-300 pl-12 pr-4 h-14 text-black placeholder-gray-500 outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 bg-gray-50"
                            >
                        </div> 

                        <!-- Tombol Login -->
                        <button @click="login" class="mt-4 w-full rounded-xl bg-blue-600 py-3 font-semibold text-white hover:bg-blue-700">
                            Login
                        </button>
                    </form> 

                    <!-- Footer Link -->
                    <p class="m-3 text-center text-gray-500">
                        Don’t have an account?
                        <RouterLink to="/register" class="font-bold text-[#1A73E8] hover:underline ml-1">Register here</RouterLink>
                    </p>

                </div>
            </div>
        </Transition>
    </div>
</template> 

<style scoped>
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