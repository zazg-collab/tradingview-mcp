"""IDX (Bursa Efek Indonesia) index constituents.

Indeks yang didukung:
  - LQ45       : 45 saham paling likuid di BEI (blue chip)
  - IDX30      : 30 saham teratas dari LQ45 (subset paling likuid)
  - IDX80      : LQ45 + 35 saham mid-cap tambahan
  - KOMPAS100  : 100 saham pilihan Kompas / BEI
  - JII        : Jakarta Islamic Index — 30 saham syariah
  - IDXHIDIV20 : 20 saham dengan dividen tinggi
  - IDXBUMN20  : 20 saham BUMN & terafiliasi

Catatan: Konstituen diperbarui tiap Februari & Agustus oleh BEI.
Data ini mencerminkan komposisi ~2025-2026.
"""
from __future__ import annotations
from typing import Callable, Dict, List


# ── LQ45 ──────────────────────────────────────────────────────────────────────
# 45 saham paling likuid, weighted by free-float market cap
LQ45_CONSTITUENTS: List[str] = [
    "IDX:AALI",    # Astra Agro Lestari
    "IDX:ADRO",    # Adaro Andalan Indonesia
    "IDX:AKRA",    # AKR Corporindo
    "IDX:AMMN",    # Amman Mineral Internasional
    "IDX:AMRT",    # Sumber Alfaria Trijaya
    "IDX:ANTM",    # Aneka Tambang
    "IDX:ASII",    # Astra International
    "IDX:BBCA",    # Bank Central Asia
    "IDX:BBNI",    # Bank Negara Indonesia
    "IDX:BBRI",    # Bank Rakyat Indonesia
    "IDX:BBTN",    # Bank Tabungan Negara
    "IDX:BJBR",    # Bank BJB
    "IDX:BJTM",    # Bank Jatim
    "IDX:BMRI",    # Bank Mandiri
    "IDX:BRIS",    # Bank Syariah Indonesia
    "IDX:BRPT",    # Barito Pacific
    "IDX:BSDE",    # Bumi Serpong Damai
    "IDX:CPIN",    # Charoen Pokphand Indonesia
    "IDX:EMTK",    # Elang Mahkota Teknologi
    "IDX:EXCL",    # XL Axiata
    "IDX:GOTO",    # GoTo Gojek Tokopedia
    "IDX:HRUM",    # Harum Energy
    "IDX:ICBP",    # Indofood CBP
    "IDX:INCO",    # Vale Indonesia
    "IDX:INDF",    # Indofood Sukses Makmur
    "IDX:INTP",    # Indocement
    "IDX:ITMG",    # Indo Tambangraya Megah
    "IDX:JPFA",    # Japfa Comfeed
    "IDX:KLBF",    # Kalbe Farma
    "IDX:MAPI",    # Map Aktif Adiperkasa
    "IDX:MBMA",    # Merdeka Battery Materials
    "IDX:MDKA",    # Merdeka Copper Gold
    "IDX:MEDC",    # Medco Energi
    "IDX:MIKA",    # Mitra Keluarga Karyasehat
    "IDX:MNCN",    # Media Nusantara Citra
    "IDX:PGAS",    # Perusahaan Gas Negara
    "IDX:PTBA",    # Bukit Asam
    "IDX:PTPP",    # PP Persero
    "IDX:SIDO",    # Sido Muncul
    "IDX:SMGR",    # Semen Indonesia
    "IDX:TLKM",    # Telkom Indonesia
    "IDX:TOWR",    # Sarana Menara Nusantara
    "IDX:TPIA",    # Chandra Asri
    "IDX:UNTR",    # United Tractors
    "IDX:UNVR",    # Unilever Indonesia
]

# ── IDX30 ─────────────────────────────────────────────────────────────────────
# 30 saham teratas dari LQ45 (yang paling liquid & market cap besar)
IDX30_CONSTITUENTS: List[str] = [
    "IDX:AMMN",
    "IDX:ANTM",
    "IDX:ASII",
    "IDX:BBCA",
    "IDX:BBNI",
    "IDX:BBRI",
    "IDX:BMRI",
    "IDX:BRIS",
    "IDX:BRPT",
    "IDX:EMTK",
    "IDX:GOTO",
    "IDX:ICBP",
    "IDX:INCO",
    "IDX:INDF",
    "IDX:ITMG",
    "IDX:KLBF",
    "IDX:MAPI",
    "IDX:MBMA",
    "IDX:MDKA",
    "IDX:MEDC",
    "IDX:MIKA",
    "IDX:PGAS",
    "IDX:PTBA",
    "IDX:SMGR",
    "IDX:TLKM",
    "IDX:TOWR",
    "IDX:TPIA",
    "IDX:UNTR",
    "IDX:UNVR",
    "IDX:ADRO",
]

# ── IDX80 ─────────────────────────────────────────────────────────────────────
# LQ45 + 35 saham mid-cap tambahan (unique tickers saja)
_IDX80_EXTRA: List[str] = [
    "IDX:ACES",    # Ace Hardware
    "IDX:ADHI",    # Adhi Karya
    "IDX:AGRO",    # BRI Agroniaga
    "IDX:ASRI",    # Alam Sutera Realty
    "IDX:AUTO",    # Astra Otoparts
    "IDX:BNGA",    # Bank CIMB Niaga
    "IDX:CTRA",    # Ciputra Development
    "IDX:DMAS",    # Puradelta Lestari
    "IDX:DSSA",    # Dian Swastatika Sentosa
    "IDX:ERAA",    # Erajaya Swasembada
    "IDX:HEAL",    # Medikaloka Hermina
    "IDX:INKP",    # Indah Kiat Pulp & Paper
    "IDX:ISAT",    # Indosat Ooredoo Hutchison
    "IDX:JSMR",    # Jasa Marga
    "IDX:MYOR",    # Mayora Indah
    "IDX:PNBN",    # Bank Panin
    "IDX:PWON",    # Pakuwon Jati
    "IDX:SCMA",    # Surya Citra Media
    "IDX:SMRA",    # Summarecon Agung
    "IDX:TBIG",    # Tower Bersama Infrastructure
    "IDX:TSPC",    # Tempo Scan Pacific
    "IDX:WIKA",    # Wijaya Karya
    "IDX:WSKT",    # Waskita Karya
    "IDX:ULTJ",    # Ultrajaya Milk
    "IDX:BUKA",    # Bukalapak
    "IDX:ARTO",    # Bank Jago
    "IDX:DCII",    # DCI Indonesia
    "IDX:PGEO",    # Pertamina Geothermal
    "IDX:BIRD",    # Blue Bird
    "IDX:DOID",    # Delta Dunia Makmur
    "IDX:GJTL",    # Gajah Tunggal
    "IDX:MIDI",    # Midi Utama Indonesia
    "IDX:SILO",    # Siloam International Hospitals
    "IDX:SMDR",    # Samudera Indonesia
    "IDX:NCKL",    # Trimegah Bangun Persada (Nikel)
]

def _get_idx80() -> List[str]:
    seen = set()
    result = []
    for s in LQ45_CONSTITUENTS + _IDX80_EXTRA:
        if s not in seen:
            seen.add(s)
            result.append(s)
    return result[:80]

IDX80_CONSTITUENTS: List[str] = _get_idx80()


# ── KOMPAS100 ─────────────────────────────────────────────────────────────────
# 100 saham pilihan (IDX80 + 20 saham tambahan)
_KOMPAS100_EXTRA: List[str] = [
    "IDX:INAI",    # Indal Aluminium
    "IDX:KAEF",    # Kimia Farma
    "IDX:LPPF",    # Matahari Dept Store
    "IDX:MKPI",    # Metropolitan Kentjana
    "IDX:MTDL",    # Metrodata Electronics
    "IDX:TKIM",    # Pabrik Kertas Tjiwi Kimia
    "IDX:ABMM",    # ABM Investama
    "IDX:AMMN",    # Amman Mineral (sudah di LQ45 — akan difilter)
    "IDX:ANTM",    # Aneka Tambang (sudah di LQ45 — akan difilter)
    "IDX:BBYB",    # Bank Neo Commerce
    "IDX:BDMN",    # Bank Danamon
    "IDX:CPIN",    # Charoen Pokphand (sudah di LQ45)
    "IDX:ELSA",    # Elnusa
    "IDX:GEMS",    # Golden Energy Mines
    "IDX:GOTO",    # GoTo (sudah di LQ45)
    "IDX:HOKI",    # Buyung Poetra Sembada
    "IDX:HRTA",    # Hartadinata Abadi
    "IDX:KIJA",    # Kawasan Industri Jababeka
    "IDX:LPKR",    # Lippo Karawaci
    "IDX:MFIN",    # Mandala Multifinance
    "IDX:MLBI",    # Multi Bintang Indonesia
    "IDX:NRCA",    # Nusa Raya Cipta
    "IDX:PPRO",    # PP Property
    "IDX:PRDA",    # Prodia Widyahusada
    "IDX:RALS",    # Ramayana Lestari Sentosa
    "IDX:SAME",    # Sarana Meditama Metropolitan
    "IDX:SMCB",    # Solusi Bangun Indonesia
    "IDX:SSMS",    # Sawit Sumbermas Sarana
    "IDX:TGRA",    # Terregra Asia Energy
    "IDX:TRIM",    # Trimegah Sekuritas
]

def _get_kompas100() -> List[str]:
    seen = set()
    result = []
    for s in IDX80_CONSTITUENTS + _KOMPAS100_EXTRA:
        if s not in seen:
            seen.add(s)
            result.append(s)
    return result[:100]

KOMPAS100_CONSTITUENTS: List[str] = _get_kompas100()


# ── JII (Jakarta Islamic Index) ────────────────────────────────────────────────
# 30 saham syariah paling likuid (Dewan Syariah Nasional)
JII_CONSTITUENTS: List[str] = [
    "IDX:AALI",    # Astra Agro Lestari
    "IDX:ADRO",    # Adaro Andalan Indonesia
    "IDX:AKRA",    # AKR Corporindo
    "IDX:AMMN",    # Amman Mineral
    "IDX:ANTM",    # Aneka Tambang
    "IDX:ASII",    # Astra International
    "IDX:BRIS",    # Bank Syariah Indonesia (khusus syariah)
    "IDX:BRPT",    # Barito Pacific
    "IDX:BSDE",    # Bumi Serpong Damai
    "IDX:CPIN",    # Charoen Pokphand
    "IDX:DSSA",    # Dian Swastatika
    "IDX:EMTK",    # Elang Mahkota Teknologi
    "IDX:EXCL",    # XL Axiata
    "IDX:GOTO",    # GoTo
    "IDX:HEAL",    # Medikaloka Hermina
    "IDX:HRUM",    # Harum Energy
    "IDX:ICBP",    # Indofood CBP
    "IDX:INCO",    # Vale Indonesia
    "IDX:ITMG",    # Indo Tambangraya Megah
    "IDX:JPFA",    # Japfa Comfeed
    "IDX:KLBF",    # Kalbe Farma
    "IDX:MAPI",    # MAP Aktif
    "IDX:MBMA",    # Merdeka Battery
    "IDX:MDKA",    # Merdeka Copper Gold
    "IDX:MEDC",    # Medco Energi
    "IDX:MIKA",    # Mitra Keluarga
    "IDX:PTBA",    # Bukit Asam
    "IDX:SMGR",    # Semen Indonesia
    "IDX:TLKM",    # Telkom Indonesia
    "IDX:TOWR",    # Sarana Menara
]


# ── IDXHIDIV20 ────────────────────────────────────────────────────────────────
# 20 saham dengan imbal hasil dividen tinggi
IDXHIDIV20_CONSTITUENTS: List[str] = [
    "IDX:AALI",    # Astra Agro
    "IDX:ADRO",    # Adaro
    "IDX:ASII",    # Astra International
    "IDX:BBCA",    # BCA
    "IDX:BBNI",    # BNI
    "IDX:BBRI",    # BRI
    "IDX:BMRI",    # Bank Mandiri
    "IDX:CPIN",    # Charoen Pokphand
    "IDX:ICBP",    # Indofood CBP
    "IDX:INDF",    # Indofood
    "IDX:ITMG",    # Indo Tambangraya
    "IDX:KLBF",    # Kalbe Farma
    "IDX:MAPI",    # MAP Aktif
    "IDX:PTBA",    # Bukit Asam
    "IDX:SMGR",    # Semen Indonesia
    "IDX:TLKM",    # Telkom
    "IDX:TOWR",    # Sarana Menara
    "IDX:UNTR",    # United Tractors
    "IDX:UNVR",    # Unilever
    "IDX:SIDO",    # Sido Muncul
]


# ── IDXBUMN20 ─────────────────────────────────────────────────────────────────
# 20 saham BUMN & terafiliasi
IDXBUMN20_CONSTITUENTS: List[str] = [
    "IDX:ADHI",    # Adhi Karya
    "IDX:AGRO",    # BRI Agroniaga
    "IDX:ANTM",    # Aneka Tambang
    "IDX:BBNI",    # BNI
    "IDX:BBRI",    # BRI
    "IDX:BBTN",    # BTN
    "IDX:BJBR",    # Bank BJB
    "IDX:BJTM",    # Bank Jatim
    "IDX:BMRI",    # Bank Mandiri
    "IDX:BRIS",    # BSI
    "IDX:INTP",    # Indocement
    "IDX:ISAT",    # Indosat
    "IDX:JSMR",    # Jasa Marga
    "IDX:KAEF",    # Kimia Farma
    "IDX:PGAS",    # PGN
    "IDX:PGEO",    # Pertamina Geothermal
    "IDX:PTBA",    # Bukit Asam
    "IDX:PTPP",    # PP Persero
    "IDX:SMGR",    # Semen Indonesia
    "IDX:TLKM",    # Telkom
]


# ── Registry ───────────────────────────────────────────────────────────────────
IDX_INDICES: Dict[str, dict] = {
    "LQ45": {
        "name": "LQ45",
        "description": "45 saham paling likuid di BEI — blue chip Indonesia",
        "constituents_count": 45,
        "get_symbols": lambda: LQ45_CONSTITUENTS,
    },
    "IDX30": {
        "name": "IDX30",
        "description": "30 saham teratas berdasarkan likuiditas dan market cap",
        "constituents_count": 30,
        "get_symbols": lambda: IDX30_CONSTITUENTS,
    },
    "IDX80": {
        "name": "IDX80",
        "description": "80 saham pilihan — LQ45 ditambah mid-cap berkualitas",
        "constituents_count": 80,
        "get_symbols": IDX80_CONSTITUENTS.copy if False else lambda: IDX80_CONSTITUENTS,
    },
    "KOMPAS100": {
        "name": "KOMPAS100",
        "description": "100 saham pilihan Kompas & BEI berdasarkan fundamental dan likuiditas",
        "constituents_count": 100,
        "get_symbols": lambda: KOMPAS100_CONSTITUENTS,
    },
    "JII": {
        "name": "Jakarta Islamic Index (JII)",
        "description": "30 saham syariah paling likuid — sesuai prinsip syariah DSN-MUI",
        "constituents_count": 30,
        "get_symbols": lambda: JII_CONSTITUENTS,
    },
    "IDXHIDIV20": {
        "name": "IDX High Dividend 20",
        "description": "20 saham dengan imbal hasil dividen tertinggi dan konsisten",
        "constituents_count": 20,
        "get_symbols": lambda: IDXHIDIV20_CONSTITUENTS,
    },
    "IDXBUMN20": {
        "name": "IDX BUMN20",
        "description": "20 saham BUMN dan perusahaan terafiliasi negara",
        "constituents_count": 20,
        "get_symbols": lambda: IDXBUMN20_CONSTITUENTS,
    },
}


def is_lq45_stock(sym: str) -> bool:
    """True jika saham masuk LQ45."""
    clean = sym.upper()
    if not clean.startswith("IDX:"):
        clean = f"IDX:{clean}"
    return clean in LQ45_CONSTITUENTS
