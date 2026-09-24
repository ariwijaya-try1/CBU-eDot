# Badan usaha yang benar-benar dipakai untuk sales operation via eSuite.
# Dipusatkan di sini supaya branch_sync_service, warehouse_sync_service &
# stock_sync_service pakai daftar yang sama.
#
# REVISI 18 Agustus 2026 -- SAP ("Sunshine Agri Pratama") ditambahkan,
# menggantikan keputusan lama "cuma 2 dari 4 company". Riwayat singkat:
# awalnya SAP dianggap murni cabang produksi (punya gudang/ikut menyimpan
# barang, TAPI tidak dianggap "melakukan bisnis" via eSuite) makanya tidak
# masuk sini. Sempat dicoba solusi partial (SAP cuma ditambahkan ke Branch
# lewat constant terpisah `BRANCH_EXTRA_COMPANY_NAMES`, supaya Warehouse/
# Stock Matrix tidak ikut meluas) -- TAPI user KEMUDIAN eksplisit
# mengoreksi: asumsi bisnis SEKARANG adalah 3 dari 4 company yang akan
# melakukan bisnis (bukan 2 lagi), jadi SAP SENGAJA digabung LANGSUNG ke
# list utama ini -- Warehouse & Stock Matrix IKUT meluas cakupannya ke SAP
# juga (bukan cuma Branch). `BRANCH_EXTRA_COMPANY_NAMES` (constant
# terpisah dari revisi sebelumnya) DIHAPUS karena sekarang redundan --
# lihat pricelist_progress.md untuk riwayat keputusan lengkap.
#
# REVISI 24 September 2026 -- scope jadi 4 company: "Sunshine Boga Utama"
# (SBU, Jakarta, res.company id 4) ditambahkan supaya eDot bisa dipakai di
# Jakarta. Klarifikasi user: "agro" = SAP (branch produksi, tanpa sales),
# "branch office luar kota" = SBU. Company ke-5 "Sunshine Group Indonesia,
# PT" (id 5, tanpa customer/warehouse/pricelist) TETAP di luar scope.
# Match pakai ilike (substring) -- "Sunshine Boga Utama" tidak bentrok
# dengan "Cahaya Boga Utama" (dicek dari hasil GET /odoo/branch).
IN_SCOPE_COMPANY_NAMES = [
    "Cahaya Boga Utama",
    "Sunshine Food and Co",
    "Sunshine Agri Pratama",
    "Sunshine Boga Utama",
]
