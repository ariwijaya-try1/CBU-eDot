from slowapi import Limiter
from slowapi.util import get_remote_address

# default_limits (28 Agustus 2026) -- AKTIVASI dari security audit 16 Agustus
# (temuan #2: Limiter ini SUDAH ADA sejak lama tapi TIDAK PERNAH didaftarkan
# ke app di main.py, jadi "false sense of security" -- nol proteksi DoS/
# brute-force nyata). 300/minute per IP dipilih GENEROUS (bukan hasil tuning
# ketat) -- tujuan utamanya cuma pasang lantai dasar proteksi (skrip
# brute-force API key / lonjakan traffic tak wajar), BUKAN membatasi
# pemakaian normal tim internal/automation n8n yang manggil endpoint ini
# terjadwal. Kalau ternyata automation batch/sync normal sering kena 429,
# NAIKKAN angka ini (bukan berarti limiter-nya salah) -- BELUM ditest live
# dengan pola traffic nyata.
limiter = Limiter(key_func=get_remote_address, default_limits=["300/minute"])
