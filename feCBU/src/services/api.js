import axios from "axios"

const api = axios.create({
    baseURL: "http://localhost:8001",

    headers:{
        "Content-Type":"application/json",
        "x-api-key":"c7a91f4e8d2b6c53f0a8e17b9d4c2f6a1e8b5d3c7f9a2e64b1c8d5f0a3e7b9c2",
    },
})

export default api