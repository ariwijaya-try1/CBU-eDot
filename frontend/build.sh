#!/bin/sh
# Dipanggil service `ui-build` (docker-compose.yml). Hasil: frontend/dist.
# Build ke dist_tmp dulu, baru ganti dist kalau sukses -> UI lama tetap jalan kalau build gagal.
set -u
cd /frontend

# npm install hanya kalau package-lock.json berubah (hash disimpan di volume node_modules)
LOCK_HASH=$(md5sum package-lock.json | cut -d' ' -f1)
if [ "$(cat node_modules/.lock-hash 2>/dev/null)" != "$LOCK_HASH" ]; then
  echo "[ui-build] install dependency..."
  if ! npm install --no-audit --no-fund; then
    echo "[ui-build] GAGAL install dependency -- UI lama tetap dipakai"
    exit 1
  fi
  echo "$LOCK_HASH" > node_modules/.lock-hash
fi

echo "[ui-build] build..."
rm -rf dist_tmp
if npx vite build --outDir dist_tmp --emptyOutDir; then
  rm -rf dist_old
  [ -d dist ] && mv dist dist_old
  mv dist_tmp dist
  rm -rf dist_old
  echo "[ui-build] SELESAI -> http://127.0.0.1:8001/ui/"
else
  rm -rf dist_tmp
  echo "[ui-build] GAGAL build -- UI lama tetap dipakai"
  exit 1
fi
