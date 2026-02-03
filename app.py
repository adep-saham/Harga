import json
import requests
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Grafik Harga Emas Pegadaian", layout="wide")
st.title("📈 Grafik Harga Emas Pegadaian")

GRAPHQL_URL = "https://agata.pegadaian.co.id/public/webcorp/konven/graphql"
REFERER = "https://pegadaian.co.id/"

QUERY_ALL_GRAFIK = """
query allGrafik {
  allGrafik {
    tipe
    time_interval
    json_fluktuasi
    updatedat
  }
}
"""

def build_headers():
    apikey = st.secrets.get("PEGADAIAN_APIKEY", "")
    bearer = st.secrets.get("PEGADAIAN_BEARER", "")
    if not apikey or not bearer:
        raise RuntimeError("Isi secrets: PEGADAIAN_APIKEY dan PEGADAIAN_BEARER")

    return {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Origin": "https://pegadaian.co.id",
        "Referer": REFERER,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120 Safari/537.36",
        "apikey": apikey,
        "authorization": f"Bearer {bearer}",
    }

def fetch_all_grafik():
    payload = {"operationName": "allGrafik", "variables": {}, "query": QUERY_ALL_GRAFIK}
    r = requests.post(GRAPHQL_URL, headers=build_headers(), json=payload, timeout=30)

    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}\n\n{r.text[:1200]}")

    resp = r.json()

    # wrapper unauthorized
    if resp.get("responseCode") and resp.get("data") is None:
        raise RuntimeError(f"Unauthorized: {resp.get('responseDesc')} ({resp.get('responseCode')})")

    if "errors" in resp:
        raise RuntimeError(json.dumps(resp["errors"], indent=2))

    if "data" in resp and "allGrafik" in resp["data"]:
        return resp["data"]["allGrafik"]

    raise RuntimeError("Response shape tidak dikenali")

def parse_json_fluktuasi(js: str):
    """
    Handle variasi:
    - { pricedlist: [...] }
    - [ { pricedlist: [...] } ]
    - [ {...}, {...} ]
    - { ... }
    """
    obj = json.loads(js)

    if isinstance(obj, list) and obj:
        first = obj[0]
        if isinstance(first, dict) and "pricedlist" in first:
            return first["pricedlist"]
        if isinstance(first, dict):
            return obj

    if isinstance(obj, dict):
        if "pricedlist" in obj:
            return obj["pricedlist"]
        return [obj]

    return []

def pick_first_existing(df: pd.DataFrame, candidates: list[str]):
    for c in candidates:
        if c in df.columns:
            return c
    return None

def auto_map(df: pd.DataFrame, tipe: str):
    """
    Coba auto-map kolom tanggal & harga untuk berbagai schema.
    Return: (mapped_df, used_date_col, used_price_cols)
    """
    # kandidat nama tanggal
    date_candidates = [
        "lastUpdate", "last_update", "updatedAt", "updatedat",
        "date", "tanggal", "time", "datetime", "x", "t"
    ]
    date_col = pick_first_existing(df, date_candidates)

    # kandidat nama harga umum
    # Kadang: harga, value, y, price, close
    price_candidates = ["harga", "value", "y", "price", "close"]

    # kandidat buy/sell
    buy_candidates = ["hargaBeli", "harga_beli", "buy", "buyPrice", "priceBuy"]
    sell_candidates = ["hargaJual", "harga_jual", "sell", "sellPrice", "priceSell"]

    buy_col = pick_first_existing(df, buy_candidates)
    sell_col = pick_first_existing(df, sell_candidates)

    # Kalau tidak ada hargaBeli/hargaJual, pakai harga/value/y dsb
    generic_price_col = pick_first_existing(df, price_candidates)

    out = pd.DataFrame()
    out["tanggal"] = pd.to_datetime(df[date_col], errors="coerce") if date_col else pd.NaT

    # Strategy:
    # - Kalau ada buy/sell dua kolom → isi dua-duanya
    # - Kalau cuma ada generic price → isi sesuai tipe (jual -> harga_jual, beli -> harga_beli)
    out["harga_beli"] = pd.NA
    out["harga_jual"] = pd.NA

    used = {"date": date_col, "buy": buy_col, "sell": sell_col, "generic": generic_price_col}

    if buy_col or sell_col:
        if buy_col:
            out["harga_beli"] = pd.to_numeric(df[buy_col], errors="coerce")
        if sell_col:
            out["harga_jual"] = pd.to_numeric(df[sell_col], errors="coerce")
    elif generic_price_col:
        if tipe.lower() == "jual":
            out["harga_jual"] = pd.to_numeric(df[generic_price_col], errors="coerce")
        else:
            out["harga_beli"] = pd.to_numeric(df[generic_price_col], errors="coerce")
    else:
        # tidak ketemu kolom harga
        pass

    out = out.sort_values("tanggal").reset_index(drop=True)
    return out, used

# UI
col1, col2, col3 = st.columns([2, 2, 1])
with col1:
    tipe = st.selectbox("Tipe", ["beli", "jual"], index=1)
with col2:
    interval = st.number_input("time_interval (contoh: 360 = 1 tahun)", min_value=1, value=360, step=1)
with col3:
    show_debug = st.checkbox("Debug", value=True)

if st.button("📥 Ambil Data Grafik"):
    records = fetch_all_grafik()

    record = next(
        (r for r in records
         if str(r.get("tipe", "")).lower() == tipe
         and int(r.get("time_interval", -1)) == int(interval)),
        None
    )

    if not record:
        st.warning("Kombinasi tidak ditemukan. Tersedia:")
        combos = sorted({(str(r.get("tipe","")).lower(), int(r.get("time_interval",-1))) for r in records})
        st.write(combos)
        st.stop()

    priced = parse_json_fluktuasi(record["json_fluktuasi"])

    if show_debug:
        st.subheader("🔎 Debug: raw parsed (sample)")
        st.code(json.dumps(priced[:3] if isinstance(priced, list) else priced, indent=2)[:2000])

    # kalau priced kosong
    if not priced:
        st.error("Parsed data kosong. Kemungkinan json_fluktuasi berisi struktur non-list/non-dict.")
        st.stop()

    df_raw = pd.DataFrame(priced)

    if show_debug:
        st.subheader("🔎 Debug: kolom asli yang diterima")
        st.write(list(df_raw.columns))
        st.dataframe(df_raw.head(10), use_container_width=True)

    # auto mapping
    out, used = auto_map(df_raw, tipe)

    if show_debug:
        st.subheader("🔎 Debug: mapping yang dipakai")
        st.json(used)

    # Jika masih kosong (harga semua NA), sediakan mapping manual
    if out[["harga_beli", "harga_jual"]].isna().all().all():
        st.warning("Auto-mapping tidak menemukan kolom harga. Pilih kolom manual di bawah.")

        cols = ["(none)"] + list(df_raw.columns)

        c1, c2, c3 = st.columns(3)
        with c1:
            date_col = st.selectbox("Kolom tanggal", cols, index=0)
        with c2:
            buy_col = st.selectbox("Kolom harga_beli (opsional)", cols, index=0)
        with c3:
            sell_col = st.selectbox("Kolom harga_jual (opsional)", cols, index=0)

        out2 = pd.DataFrame()
        out2["tanggal"] = pd.to_datetime(df_raw[date_col], errors="coerce") if date_col != "(none)" else pd.NaT
        out2["harga_beli"] = pd.to_numeric(df_raw[buy_col], errors="coerce") if buy_col != "(none)" else pd.NA
        out2["harga_jual"] = pd.to_numeric(df_raw[sell_col], errors="coerce") if sell_col != "(none)" else pd.NA
        out2 = out2.sort_values("tanggal").reset_index(drop=True)

        out = out2

    st.success(f"Berhasil! Total data: {len(out)}")
    st.dataframe(out, use_container_width=True)

    st.download_button(
        "⬇️ Download CSV",
        data=out.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"pegadaian_grafik_{tipe}_{interval}.csv",
        mime="text/csv",
    )
