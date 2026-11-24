# Deploy Bridge + Edot Bridge UI

Satu folder aplikasi (root repo `eDot_cbu_fastapi`) berisi API dan UI. Salin folder ini ke server, isi `.env`, jalankan Docker.

## Isi folder yang disalin

```
eDot_cbu_fastapi/
├── app/                 # bridge FastAPI
├── frontend/            # Edot Bridge UI (Vue) -- TANPA node_modules/ dan dist/
├── Dockerfile
├── docker-compose.yml   # service app + ui-build
├── requirements.txt
├── .dockerignore
├── .gitignore
└── .env.example         # di server: salin jadi .env lalu isi
```

Tidak perlu disalin: `frontend/node_modules/`, `frontend/dist/`, `logs/`, `__pycache__/`, `.git/` (kecuali deploy pakai git).

## Pertama kali di server

```bash
cp .env.example .env        # lalu isi nilai Odoo, eSuite, API_KEY
docker compose up -d --build
docker compose logs ui-build   # tunggu "[ui-build] SELESAI"
```

Server butuh internet saat build pertama (npm registry + pip).
Buka di browser server: `http://127.0.0.1:8001/ui/` (Swagger: `/docs`). Port hanya terbuka untuk server itu sendiri.

## Update kode

1. Salin file/folder yang berubah (timpa).
2. `docker compose restart` -> API reload + UI build ulang.
3. Kalau `requirements.txt` atau `Dockerfile` berubah: `docker compose up -d --build`.

`npm install` otomatis hanya kalau `frontend/package-lock.json` berubah.

## Cek & troubleshoot

- Status: `docker compose ps` (`ui-build` memang berhenti setelah build; `Exited (0)` = sukses, `Exited (1)` = gagal, UI lama tetap dipakai).
- Log: `docker compose logs app` / `docker compose logs ui-build`.
- `/ui/` menampilkan "UI belum di-build" -> cek log `ui-build`.
- Setelah server reboot, `app` jalan otomatis (`restart: always`); UI tidak perlu build ulang (`frontend/dist` tetap ada).
- Linux: `frontend/dist` dibuat oleh container (root). Hapus folder aplikasi pakai `sudo` bila perlu.
