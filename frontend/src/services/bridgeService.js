import http from './http'

// GET / bridge: kena global verify_api_key -> dipakai untuk cek API key valid + bridge hidup
export async function checkBridge(apiKey) {
  const headers = apiKey ? { 'x-api-key': apiKey } : {}
  const { data } = await http.get('/', { headers })
  return data
}

// /openapi.json tidak butuh API key; dipakai untuk ringkasan endpoint per grup Swagger
export async function getOpenApi() {
  const { data } = await http.get('/openapi.json')
  return data
}
