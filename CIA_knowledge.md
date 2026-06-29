# CIA (Chronic Investor Academy) — Knowledge Base Lengkap
> Disintesis dari: PDF Materi TA 2026 (112 hal), History Diskusi Antigravity AI, Telegram CIA Saham, $Diary MOMENTUM, $ #ALERT CIA lounge, $Behind the scene riset
> Last updated: 2026-06-29

---

## 1. FILOSOFI DASAR CIA

**CIA = Chronic Investor Academy** — metode trading momentum saham IDX yang dikembangkan sejak 2008 oleh Tradingdiary2 (Pak T).

**Prinsip utama:**
- Ikuti bandar/smart money, bukan melawan arah
- Beli saham yang sudah terbukti naik (trending up), bukan yang "murah"
- MA (Moving Average) adalah peta jalan: posisi harga vs MA menentukan keputusan
- Cash adalah posisi — tidak selalu harus fully invested
- **MILD time** (ranging/konsolidasi) = waktu ENTRY
- **WILD time** (trending) = waktu EXIT/ambil profit

---

## 2. SETUP MA — HIERARKI KEKUATAN

CIA menggunakan MA3, MA5, MA10, MA20, MA50, MA100, MA200 (dan MA400 untuk konteks jangka panjang).

### 2.1 Above All MA (Original CIA since 2008)
- **Syarat:** Harga di atas MA3, MA5, MA20, MA50, MA100, MA200
- **Makna:** Saham mulai trending up di semua timeframe
- **Setup entry awal** — milestone pertama yang harus dicari

### 2.2 SUPERKETAT ⚡ (Setup Entry Terbaik)
- **Syarat (AND condition — semua harus terpenuhi):**
  - Harga di atas MA3 AND MA5 AND MA10 AND MA20
  - Jarak harga ke SEMUA MA tersebut ≤ 5%
- **Makna:** Semua MA sudah rapat, harga "menguncup" = titik energi tertinggi sebelum breakout
- **CL (Cut Loss):** Di bawah semua MA (karena semua rapat, CL jadi sangat kecil)
- **Risk/Reward:** Terbaik — risiko kecil, potensi besar
- Ini adalah **konfirmasi konsolidasi selesai** sebelum ledakan berikutnya

### 2.3 KETAT (Konfirmasi Tren Mulai)
- **Syarat (OR condition — salah satu cukup):**
  - Harga di atas MA3, MA5, MA10, MA20
  - Jarak ≤ 5% ke MA3/MA5/MA10 **OR** ke MA20
- **Makna:** Tren mulai berjalan, tapi belum sekompak superketat
- **Bedanya dengan Superketat:** Ketat = OR, Superketat = AND (semua MA rapat sekaligus)

### 2.4 THEONE (Second Ketat)
- Ketat yang terjadi untuk **kedua kalinya** setelah ada jeda
- Konfirmasi lebih kuat — saham sudah terbukti "mau jalan"
- Lebih reliabel karena sudah ada riwayat response positif

### 2.5 SUNFLOWER 🌻 (First Signal)
- Candle **ketat pertama** setelah lama tidak ketat (awal sinyal)
- Bisa jadi early entry, tapi belum sekuat theone
- Monitor untuk konfirmasi berikutnya

### 2.6 RAINBOW 🌈 (Reward Tanpa Batas)
- **Syarat:** Harga di atas SEMUA MA (MA3, MA5, MA10, MA20, MA50, MA100, MA200)
- **Tidak ada resistance MA di atas** = "langit batasnya"
- Setup untuk saham yang sudah dalam uptrend kuat
- Bisa dihold sampai ada sinyal lemah (turun di bawah MA tertentu)
- **Contoh dari Pak T:** DSSA — "selama di atas MA20, hold, CL di bawah MA20"

---

## 3. VOLUME SETUP

### 3.1 KAMEHAMEHA 💥 (Volume Explosion)
- **Syarat:** Volume hari ini >> rata-rata volume 60 hari (V60) — ledakan signifikan
- **PENTING:** Kamehameha **BISA terjadi tanpa ketat/superketat** — ini setup independen
- **Makna:** Smart money/bandar masuk dalam jumlah besar
- **Konteks:** Biasanya terjadi di area harga yang strategis (breakout level, support MA, dll)
- **Risk:** Jika terjadi tanpa konfirmasi MA setup, bisa lebih spekulatif

### 3.2 STAR ⭐ (Setup Premium Terkuat)
- **= Kamehameha + Ketat sekaligus**
- Volume explosion DAN posisi MA kompak → kombinasi sempurna
- Probability terbaik untuk ARA atau kenaikan signifikan
- Ini yang paling dicari CIA member setiap hari

### 3.3 EMPTY ZONE (Jebakan Retailer)
- Volume dan harga **flat** setelah sebelumnya sudah ARA
- Retailer lama masih hold sambil nunggu lanjutan
- Bandar sudah selesai distribusi → harga kemungkinan turun
- Kebalikan dari Kamehameha — ini sinyal **distribusi terselubung**

---

## 4. SIKLUS WYCKOFF (Landasan Teori)

```
ACCUMULATION → MARK-UP → DISTRIBUTION → MARK-DOWN → (ulang)
```

- **Accumulation:** Bandar beli diam-diam, harga sideways/ranging (MILD time)
- **Mark-up:** Harga trending naik, entry CIA (WILD time untuk profit taking)
- **Distribution:** Bandar jual ke retailer euforia, volume tinggi tapi tidak berlanjut
- **Mark-down:** Harga turun, retailer stuck

**CIA strategy:** Ikut accumulation late stage → ambil profit di mark-up.

---

## 5. CIAbot — COMMAND DAN FORMAT ALERT

### 5.1 Command `/c [ticker]`
Format output ciaagentbot:
```
R3 [TF] ma/bb : [price] [%]   ← Resistance 3 (terjauh)
R2 [TF] ma/bb : [price] [%]   ← Resistance 2
R1 [TF] ma/bb : [price] [%]   ← Resistance 1 (terdekat)

Close: [price] ([%change])

S1 [TF] ma/bb : [price] [%]   ← Support 1 (terdekat)
S2 [TF] ma/bb : [price] [%]   ← Support 2
S3 [TF] ma/bb : [price] [%]   ← Support 3 (terjauh)

ma20 : [price] ([% dari harga])
ma50 : [price] ([%])
ma100: [price] ([%])
ma200: [price] ([%])
ma400: [price] ([%])

ratio (ttm): ...valuation...
```
TF prefix: `Dy` = Daily, `Wy` = Weekly, `My` = Monthly

### 5.2 Alert Format ($Diary MOMENTUM — ciaagentbot alerts)
```
💚  $TICKER naik > maXX (price) now: current_price res: [MA yg masih jadi resistance]
❗  $TICKER turun <= maXX (price) now: current_price support: [MA yg jadi support]
fast $TICKER (buy_date) tp-N-of-M target_price High: high_price TP berikut: next_tp 💰
fast $TICKER (buy_date) cl PRICE Low: low_price ❗
```

### 5.3 Command Lain ciaagentbot
- `/3 [ticker]` → info lengkap + broker flow (T3)
- `/5 [ticker]` → info + broker flow (T5)  
- `/c [ticker]` → support/resistance levels
- `/iv [ticker]` → insider volume
- `/bsh [ticker]` → broker share history
- `/q [ticker]` → quick quote
- `/y [ticker]` → yearly data
- `/mm [ticker]` → market maker data

---

## 6. SOP IHSG BEARISH — CAPITAL PRESERVATION

**Aturan wajib saat IHSG di bawah semua MA:**
- Cash 80-90% portofolio
- Hanya hold saham yang tetap di atas MA20 atau MA50 atau MA100 atau MA200
- CL tanpa pikir panjang jika saham turun di bawah MA yang jadi acuan

**Konteks saat ini (29 Juni 2026):**
- Tradingdiary2: *"IHSG masih di bawah semua MA dan MA20, IHSG masih bearish"*
- Rekomendasi: *"Cash 80-90%, awasi ketat dan superketat yang di atas MA20 atau MA50 atau MA100 atau MA200"*
- Saham yang masih diperhatikan: EPAC, PNLF, SMIL, GRIA, CRAB, ICON, MPIX, SRSN, TOTL

---

## 7. CARA MENCARI SAHAM POTENSI ARA — WORKFLOW CIA

### Step 1: Filter Universe
Scan seluruh IDX (~866 saham) untuk kondisi:
- Harga di atas MA20 (minimal) — ini syarat dasar IHSG bearish
- Volume hari ini > rata-rata (V60) → tanda aktivitas

### Step 2: Cari Setup Terkuat
Priority order (terkuat → termudah):
1. **STAR** = Ketat + Kamehameha → potensi ARA tertinggi
2. **Superketat** = semua MA rapat, entry risiko kecil
3. **Ketat** = tren mulai, entry dengan CL di bawah MA
4. **Kamehameha** saja = volume spike tanpa ketat (lebih spekulatif)
5. **Rainbow** = sudah above all MA, hold atau entry pullback

### Step 3: Konfirmasi Kualitas
- Cek sektor — saham dengan sektor kuat lebih reliable
- Cek Wyckoff: apakah masih di fase accumulation atau sudah mark-up?
- Cek broadening top: jika sudah terlalu tinggi dari MA, risiko meningkat

### Step 4: Entry dan CL
- **Superketat:** Entry di level harga, CL di bawah semua MA (sangat ketat, losses kecil)
- **Ketat biasa:** CL di bawah MA yang relevan (biasanya MA kecil/higher low sebelumnya)
- **Kamehameha:** CL di bawah low bar kamehameha atau MA terdekat
- **Rainbow:** CL di bawah MA20 (Pak T: "selama di atas MA20 hold")

### Step 5: TP (Take Profit)
- **T1:** 5-10% (di atas MA terdekat berikutnya sebagai resistance)
- **T2:** 15-25% (di atas MA lebih jauh)
- **ARA potensial:** Jika ada STAR setup + IHSG supportive → bisa ke 25-35% sehari
- Trailing stop: naikkan CL ke MA lebih kecil seiring kenaikan harga

---

## 8. RISET LANJUTAN — BEHIND THE SCENE

CIA tidak hanya TA murni, ada layer riset tambahan:

### 8.1 Broker Flow Analysis (dari $Behind the scene riset)
- **BidBot tracking:** Pantau broker dominan (Top1/Top3/T5), net flow, accumulation/distribution pattern
- **Accumulation Score:** Daily, Weekly, Composite — cari yang semua positif
- **DH/AK/GR tracking:** Kode broker spesifik yang diikuti karena "smart"
- **Pattern:** CONSISTENT accumulation selama 20+ hari dari satu broker = sinyal kuat
- Contoh: UNTR → Broker AK akumulasi 209,050 lots selama 30 hari, 24 hari akumulasi vs 6 hari distribusi = sinyal kuat

### 8.2 Ownership Analysis
- Free float kecil (< 30%) = lebih mudah digerakkan
- Major holder > 50% satu entitas = relatif aman dari distribusi mendadak
- Contoh PNLF: PT PANINVEST 52.47% + PANINVEST TBK 15.19% → total insider 67.66%

### 8.3 Valuation Check (PBV)
- CIAbot menampilkan `minpbv` dan `maxpbv` historis
- Entry saat PBV mendekati minimum historis → risiko downside lebih kecil
- Contoh: PNLF PBV 0.22 (historis min PBV 0.8 bukan current) → murah secara historis

---

## 9. CONTOH REAL-TIME DISKUSI

### DSSA (29 Jun 2026)
- Harga 835, MA20 jauh di bawah (743 = -11%)
- Pak T: "selama di atas MA20, hold, CL di bawah MA20"
- P.W.: "di MA20 belinya (ideal entry)"
- Thesar: "kalau balik ke MA20 berarti harus konsol lagi untuk ngumpulin MA kecil"
- **CL rule:** "CL dekat 790" (lower high sebelumnya, bukan MA20 yang masih jauh)
- *Lesson:* Jika MA20 jauh, CL bisa pakai higher low sebelumnya sebagai proxy

### BIPI
- Pak T beli di 125 → menunggu konfirmasi
- MA20 di atas harga (148 vs harga 127) → belum di atas MA20
- Masih spekulatif entry sebelum tembus MA20
- *Lesson:* Entry di bawah MA20 = lebih berisiko, harus lebih kecil posisi

### FITT (27 Jun 2026)
- Harga 390, MA50 = 399 (harga di bawah sedikit), MA20 = 363 (harga di atas)
- Insider masif masuk Des 2025 (300-327M saham)
- Broker analysis: Day T3 Big Accumulation +24.69%
- *Lesson:* Insider movement + broker accumulation bisa jadi sinyal dini sebelum MA setup sempurna

---

## 10. TOOLS DAN IMPLEMENTATION (MCP)

### Tool yang sudah dibuat: `idx_top_gainers_losers`
- Scan 866 saham IDX via tradingview_screener.Query
- Parameter: mode (gainers/losers), timeframe, limit, min_change_pct, min_volume_idr, index_filter
- Output: ticker, name, price, change_pct, volume_idr, rsi, ma_pos, sector

### Screening CIA Setup (yang perlu dibangun):
```python
# Filter superketat:
# close > ma3 AND close > ma5 AND close > ma10 AND close > ma20
# (close - ma3)/close <= 0.05 AND
# (close - ma5)/close <= 0.05 AND
# (close - ma10)/close <= 0.05 AND
# (close - ma20)/close <= 0.05

# Filter kamehameha:
# volume today > N * volume_60_avg (N = 2-3x minimal)
```

### CIAbot Commands (via Telegram MCP — READ ONLY):
- `/c TICKER` → support/resistance levels
- `/3 TICKER` atau `/5 TICKER` → full analysis dengan broker flow
- Read dari: $Diary MOMENTUM, $ #ALERT CIA lounge, $Behind the scene riset

---

## 11. GLOSSARY

| Term | Definisi |
|------|----------|
| ARA | Auto Reject Atas — limit atas IDX (25-35% per hari) |
| CL | Cut Loss — jual rugi sesuai level yang sudah ditentukan |
| MA | Moving Average (MA3, MA5, MA10, MA20, MA50, MA100, MA200, MA400) |
| Ketat | Harga di atas MA3/5/10/20, jarak ≤5% ke salah satu MA (OR) |
| Superketat | Harga di atas MA3/5/10/20, jarak ≤5% ke SEMUA MA (AND) |
| Kamehameha | Volume ledakan vs V60 rata-rata |
| STAR ⭐ | Ketat + Kamehameha di hari yang sama |
| Rainbow 🌈 | Above all MA, tidak ada resistance di atas |
| Theone | Second ketat (lebih reliabel) |
| Sunflower 🌻 | First ketat setelah lama tidak ketat |
| Empty Zone | Volume flat setelah ARA — jebakan retailer |
| MILD time | Fase ranging/konsolidasi = waktu entry |
| WILD time | Fase trending = waktu exit/profit |
| V60 | Rata-rata volume 60 hari (benchmark kamehameha) |
| Broadening Top | Pola divergen high-low yang semakin lebar — bahaya |
| Higher Low | Low yang lebih tinggi dari sebelumnya = tren up masih valid |

---

## 12. WATCHLIST AKTIF (per 29 Jun 2026)

Saham yang diperhatikan CIA saat IHSG bearish (masih di atas MA tertentu):
- **EPAC, PNLF, SMIL, GRIA, CRAB, ICON, MPIX, SRSN, TOTL** (dari $Diary MOMENTUM)
- **DSSA** — di atas MA20, hold dengan CL 790
- **KOCI, UNTR, OILS, PANS, ESIP, MMIX** — dari scan CIA Saham group
- **BIPI** — masih di bawah MA20, lebih spekulatif

---

*Sumber: PDF Materi TA 2026 CIA, diskusi Antigravity AI 29 Jun 2026, Telegram CIA Saham (materi kelas TA 2026), $Diary MOMENTUM, $ #ALERT CIA lounge, $Behind the scene riset*
