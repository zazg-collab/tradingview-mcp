"""IDX (Bursa Efek Indonesia) sector classification.

Menggunakan klasifikasi sektoral resmi BEI (IDX Sectoral):
  1. Energi
  2. Barang Baku (Basic Materials)
  3. Perindustrian (Industrials)
  4. Barang Konsumen Primer (Consumer Staples)
  5. Barang Konsumen Non-Primer (Consumer Discretionary)
  6. Kesehatan (Healthcare)
  7. Keuangan (Financials)
  8. Properti & Real Estat
  9. Teknologi
  10. Infrastruktur
  11. Transportasi & Logistik
"""
from __future__ import annotations
from typing import Dict

# ── Sector mapping: clean ticker (no IDX: prefix) → sektor BEI ────────────────
IDX_SECTOR_MAP: Dict[str, str] = {

    # ── Energi ─────────────────────────────────────────────────────────────────
    "ADRO": "energi",          # Adaro Andalan Indonesia
    "PTBA": "energi",          # Bukit Asam
    "ITMG": "energi",          # Indo Tambangraya Megah
    "MEDC": "energi",          # Medco Energi
    "HRUM": "energi",          # Harum Energy
    "PGAS": "energi",          # Perusahaan Gas Negara
    "INCO": "energi",          # Vale Indonesia
    "PGEO": "energi",          # Pertamina Geothermal Energy
    "BUMI": "energi",          # Bumi Resources
    "MBMA": "energi",          # Merdeka Battery Materials
    "ELSA": "energi",          # Elnusa
    "RAJA": "energi",          # Rukun Raharja
    "AKRA": "energi",          # AKR Corporindo
    "DSSA": "energi",          # Dian Swastatika Sentosa
    "BORN": "energi",          # Borneo Lumbung Energi & Metal
    "KKGI": "energi",          # Resource Alam Indonesia
    "MYOH": "energi",          # Samindo Resources
    "GEMS": "energi",          # Golden Energy Mines
    "BYAN": "energi",          # Bayan Resources
    "AADI": "energi",          # Adaro Andalan Indonesia (listing baru)
    "PTIS": "energi",          # Indo Straits

    # ── Barang Baku ────────────────────────────────────────────────────────────
    "ANTM": "barang_baku",     # Aneka Tambang
    "TPIA": "barang_baku",     # Chandra Asri Petrochemical
    "BRPT": "barang_baku",     # Barito Pacific
    "AMMN": "barang_baku",     # Amman Mineral Internasional
    "MDKA": "barang_baku",     # Merdeka Copper Gold
    "INTP": "barang_baku",     # Indocement Tunggal Prakarsa
    "SMGR": "barang_baku",     # Semen Indonesia
    "INKP": "barang_baku",     # Indah Kiat Pulp & Paper
    "TKIM": "barang_baku",     # Pabrik Kertas Tjiwi Kimia
    "FASW": "barang_baku",     # Fajar Surya Wisesa
    "ALDO": "barang_baku",     # Alkindo Naratama
    "KRAS": "barang_baku",     # Krakatau Steel
    "NIKL": "barang_baku",     # Treasure Indonesia / Nickel Industries
    "ARCI": "barang_baku",     # Archi Indonesia
    "INAI": "barang_baku",     # Indal Aluminium Industry
    "SMCB": "barang_baku",     # Solusi Bangun Indonesia
    "TGRA": "barang_baku",     # Terregra Asia Energy
    "DOID": "barang_baku",     # Delta Dunia Makmur
    "ABMM": "barang_baku",     # ABM Investama
    "NCKL": "barang_baku",     # Trimegah Bangun Persada
    "CUAN": "barang_baku",     # Petrindo Jaya Kreasi
    "BSML": "barang_baku",     # Bumi Suksesindo Mining
    "HRTA": "barang_baku",     # Hartadinata Abadi

    # ── Perindustrian ──────────────────────────────────────────────────────────
    "ASII": "perindustrian",   # Astra International
    "UNTR": "perindustrian",   # United Tractors
    "TOWR": "perindustrian",   # Sarana Menara Nusantara
    "TBIG": "perindustrian",   # Tower Bersama Infrastructure
    "WIKA": "perindustrian",   # Wijaya Karya
    "PTPP": "perindustrian",   # PP Persero
    "WSKT": "perindustrian",   # Waskita Karya
    "ADHI": "perindustrian",   # Adhi Karya
    "NRCA": "perindustrian",   # Nusa Raya Cipta
    "KIJA": "perindustrian",   # Kawasan Industri Jababeka
    "SSIA": "perindustrian",   # Surya Semesta Internusa
    "CTRA": "perindustrian",   # (juga properti) Ciputra Development
    "SCMA": "perindustrian",   # Surya Citra Media
    "MNCN": "perindustrian",   # Media Nusantara Citra
    "GJTL": "perindustrian",   # Gajah Tunggal
    "SMSM": "perindustrian",   # Selamat Sempurna
    "INDS": "perindustrian",   # Indospring
    "AUTO": "perindustrian",   # Astra Otoparts
    "IMAS": "perindustrian",   # Indomobil Sukses Internasional

    # ── Barang Konsumen Primer ─────────────────────────────────────────────────
    "UNVR": "barang_konsumen_primer",  # Unilever Indonesia
    "ICBP": "barang_konsumen_primer",  # Indofood CBP Sukses Makmur
    "INDF": "barang_konsumen_primer",  # Indofood Sukses Makmur
    "MYOR": "barang_konsumen_primer",  # Mayora Indah
    "SIDO": "barang_konsumen_primer",  # Industri Jamu & Farmasi Sido Muncul
    "JPFA": "barang_konsumen_primer",  # Japfa Comfeed Indonesia
    "CPIN": "barang_konsumen_primer",  # Charoen Pokphand Indonesia
    "ULTJ": "barang_konsumen_primer",  # Ultrajaya Milk Industry
    "MLBI": "barang_konsumen_primer",  # Multi Bintang Indonesia
    "ADES": "barang_konsumen_primer",  # Akasha Wira International
    "AISA": "barang_konsumen_primer",  # FKS Food and Agri
    "CAMP": "barang_konsumen_primer",  # Campina Ice Cream Industry
    "SKBM": "barang_konsumen_primer",  # Sekar Bumi
    "SKLT": "barang_konsumen_primer",  # Sekar Laut
    "DMND": "barang_konsumen_primer",  # Diamond Food Indonesia
    "HOKI": "barang_konsumen_primer",  # Buyung Poetra Sembada
    "AALI": "barang_konsumen_primer",  # Astra Agro Lestari
    "LSIP": "barang_konsumen_primer",  # PP London Sumatra Indonesia
    "SSMS": "barang_konsumen_primer",  # Sawit Sumbermas Sarana
    "TAPG": "barang_konsumen_primer",  # Triputra Agro Persada
    "DSNG": "barang_konsumen_primer",  # Dharma Satya Nusantara

    # ── Barang Konsumen Non-Primer ─────────────────────────────────────────────
    "MAPI": "barang_konsumen_non_primer",  # Map Aktif Adiperkasa
    "ACES": "barang_konsumen_non_primer",  # Ace Hardware Indonesia
    "AMRT": "barang_konsumen_non_primer",  # Sumber Alfaria Trijaya
    "LPPF": "barang_konsumen_non_primer",  # Matahari Department Store
    "ERAA": "barang_konsumen_non_primer",  # Erajaya Swasembada
    "RALS": "barang_konsumen_non_primer",  # Ramayana Lestari Sentosa
    "BATA": "barang_konsumen_non_primer",  # Sepatu Bata
    "MAPA": "barang_konsumen_non_primer",  # Map Aktif (operasional)
    "MIDI": "barang_konsumen_non_primer",  # Midi Utama Indonesia
    "HERO": "barang_konsumen_non_primer",  # Hero Supermarket
    "MCAS": "barang_konsumen_non_primer",  # M Cash Integrasi
    "KINO": "barang_konsumen_non_primer",  # Kino Indonesia
    "DYAN": "barang_konsumen_non_primer",  # Dyandra Media International
    "BAYU": "barang_konsumen_non_primer",  # Bayu Buana

    # ── Kesehatan ──────────────────────────────────────────────────────────────
    "KLBF": "kesehatan",       # Kalbe Farma
    "MIKA": "kesehatan",       # Mitra Keluarga Karyasehat
    "HEAL": "kesehatan",       # Medikaloka Hermina
    "TSPC": "kesehatan",       # Tempo Scan Pacific
    "DVLA": "kesehatan",       # Darya-Varia Laboratoria
    "KAEF": "kesehatan",       # Kimia Farma
    "PYFA": "kesehatan",       # Pyridam Farma
    "PRDA": "kesehatan",       # Prodia Widyahusada
    "OMED": "kesehatan",       # Omedics
    "SILO": "kesehatan",       # Siloam International Hospitals
    "SAME": "kesehatan",       # Sarana Meditama Metropolitan

    # ── Keuangan ───────────────────────────────────────────────────────────────
    "BBCA": "keuangan",        # Bank Central Asia
    "BBRI": "keuangan",        # Bank Rakyat Indonesia
    "BMRI": "keuangan",        # Bank Mandiri
    "BBNI": "keuangan",        # Bank Negara Indonesia
    "BRIS": "keuangan",        # Bank Syariah Indonesia
    "BBTN": "keuangan",        # Bank Tabungan Negara
    "BJBR": "keuangan",        # Bank Pembangunan Daerah Jawa Barat
    "BJTM": "keuangan",        # Bank Pembangunan Daerah Jawa Timur
    "PNBN": "keuangan",        # Bank Pan Indonesia (Panin)
    "BNII": "keuangan",        # Maybank Indonesia
    "BNGA": "keuangan",        # Bank CIMB Niaga
    "BDMN": "keuangan",        # Bank Danamon Indonesia
    "MEGA": "keuangan",        # Bank Mega
    "NISP": "keuangan",        # Bank OCBC NISP
    "AGRO": "keuangan",        # Bank Rakyat Indonesia Agroniaga
    "BKSW": "keuangan",        # Bank QNB Indonesia
    "BCIC": "keuangan",        # Bank Jtrust Indonesia
    "ARTO": "keuangan",        # Bank Jago (digital bank)
    "BBYB": "keuangan",        # Bank Neo Commerce
    "BANK": "keuangan",        # Bank Aladin Syariah
    "MCOR": "keuangan",        # Bank China Construction Bank Indonesia
    "DNAR": "keuangan",        # Bank Oke Indonesia
    "FREN": "keuangan",        # SmartFren Telecom? No, this is tech/infra
    "PANS": "keuangan",        # Panin Sekuritas
    "TRIM": "keuangan",        # Trimegah Sekuritas Indonesia
    "MFIN": "keuangan",        # Mandala Multifinance
    "BFIN": "keuangan",        # BFI Finance Indonesia
    "ADMF": "keuangan",        # Adira Dinamika Multi Finance
    "VRNA": "keuangan",        # Verena Multi Finance
    "JSMR": "keuangan",        # Jasa Marga (juga infrastruktur)
    "SMMA": "keuangan",        # Sinarmas Multiartha

    # ── Properti & Real Estat ──────────────────────────────────────────────────
    "BSDE": "properti",        # Bumi Serpong Damai
    "SMRA": "properti",        # Summarecon Agung
    "PWON": "properti",        # Pakuwon Jati
    "ASRI": "properti",        # Alam Sutera Realty
    "LPKR": "properti",        # Lippo Karawaci
    "DMAS": "properti",        # Puradelta Lestari
    "JRPT": "properti",        # Jaya Real Property
    "MTLA": "properti",        # Metropolitan Land
    "PPRO": "properti",        # PP Property
    "CTRA": "properti",        # Ciputra Development
    "APLN": "properti",        # Agung Podomoro Land
    "BIPP": "properti",        # Bhuwanatala Indah Permai
    "MDLN": "properti",        # Modernland Realty
    "PLIN": "properti",        # Plaza Indonesia Realty
    "FMII": "properti",        # Fortune Mate Indonesia
    "DUTI": "properti",        # Duta Pertiwi
    "GPRA": "properti",        # Perdana Gapuraprima
    "MKPI": "properti",        # Metropolitan Kentjana
    "RODA": "properti",        # Pikko Land Development
    "LPCK": "properti",        # Lippo Cikarang

    # ── Teknologi ──────────────────────────────────────────────────────────────
    "GOTO": "teknologi",       # GoTo Gojek Tokopedia
    "EMTK": "teknologi",       # Elang Mahkota Teknologi
    "BUKA": "teknologi",       # Bukalapak.com
    "MTDL": "teknologi",       # Metrodata Electronics
    "WIFI": "teknologi",       # Solusi Net Internusa
    "INET": "teknologi",       # Indointernet
    "AXIO": "teknologi",       # Axioo International
    "DMMX": "teknologi",       # Digital Media Nusantara
    "DCII": "teknologi",       # DCI Indonesia
    "ATIC": "teknologi",       # Anabatic Technologies
    "EDGE": "teknologi",       # Edge International Media

    # ── Infrastruktur ──────────────────────────────────────────────────────────
    "TLKM": "infrastruktur",   # Telkom Indonesia
    "EXCL": "infrastruktur",   # XL Axiata
    "ISAT": "infrastruktur",   # Indosat Ooredoo Hutchison
    "FREN": "infrastruktur",   # Smartfren Telecom
    "LINK": "infrastruktur",   # Link Net
    "SUPR": "infrastruktur",   # Solusi Tunas Pratama
    "BTEL": "infrastruktur",   # Bakrie Telecom
    "IPCC": "infrastruktur",   # Indonesia Kendaraan Terminal
    "BIRD": "infrastruktur",   # Blue Bird
    "NELY": "infrastruktur",   # Pelayaran Nelly Dwi Putri

    # ── Transportasi & Logistik ────────────────────────────────────────────────
    "SMDR": "transportasi",    # Samudera Indonesia
    "TMAS": "transportasi",    # Pelayaran Tempuran Emas
    "HITS": "transportasi",    # Humpuss Intermoda Transportasi
    "WEHA": "transportasi",    # Weha Transportasi Indonesia
    "GIAA": "transportasi",    # Garuda Indonesia
    "CMPP": "transportasi",    # AirAsia Indonesia
    "SHIP": "transportasi",    # Sillo Maritime Perdana
    "PSSI": "transportasi",    # Pelita Samudera Shipping
    "HAIS": "transportasi",    # Hasnur Internasional Shipping
    "DEAL": "transportasi",    # Dewata Freight International
    "SAPX": "transportasi",    # Satria Antaran Prima
    "KEJU": "transportasi",    # Mulia Boga Raya? No — actually KEJU is food
}

# Fix KEJU - it's food
IDX_SECTOR_MAP["KEJU"] = "barang_konsumen_primer"
# Fix FREN — duplicate, remove from keuangan (was incorrectly added)
# Already set to infrastruktur in the dict (last assignment wins in Python)


def _clean(sym: str) -> str:
    """Remove IDX: prefix and normalize."""
    return sym.upper().replace("IDX:", "").strip()


def get_sector(sym: str) -> str:
    """Return BEI sector for a given ticker. Returns 'lainnya' if unknown."""
    return IDX_SECTOR_MAP.get(_clean(sym), "lainnya")


def get_currency(_sym: str) -> str:
    """All IDX stocks trade in IDR."""
    return "IDR"


# Human-readable sector labels (for display)
SECTOR_LABELS: dict[str, str] = {
    "energi":                    "Energi",
    "barang_baku":               "Barang Baku",
    "perindustrian":             "Perindustrian",
    "barang_konsumen_primer":    "Barang Konsumen Primer",
    "barang_konsumen_non_primer":"Barang Konsumen Non-Primer",
    "kesehatan":                 "Kesehatan",
    "keuangan":                  "Keuangan",
    "properti":                  "Properti & Real Estat",
    "teknologi":                 "Teknologi",
    "infrastruktur":             "Infrastruktur",
    "transportasi":              "Transportasi & Logistik",
    "lainnya":                   "Lainnya",
}


def get_sector_label(sym: str) -> str:
    """Return human-readable sector label."""
    return SECTOR_LABELS.get(get_sector(sym), "Lainnya")
