# app.py
# =========================================
# Grafik Harga Emas Pegadaian (FINAL)
# - Endpoint: agata.pegadaian.co.id
# - Auth: apikey + bearer token (JWT)
# - Data: json_fluktuasi -> priceList[]
# =========================================
# Requirements:
#   pip install streamlit requests pandas
#
# Streamlit Secrets (WAJIB):
#   PEGADAIAN_APIKEY = "apikey dari DevTools"
#   PEGADAIAN_BEARER = "JWT token TANPA kata Bearer"
# =========================================

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
        raise RuntimeError(
            "Secrets belum lengkap. Isi PEGADAIAN_APIKEY dan PEGADAIAN_BEARER di Streamlit Secrets."
        )

    return {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Origin": "https://pegadaian.co.id",
        "Referer": REFERER,
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        # wajib (case-sensitive di backend)
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
        raise RuntimeError(
            f"Unauthorized / Token Invalid\n"
            f"responseCode={resp.get('responseCode')}\n"
            f"responseDesc={resp.get('responseDesc')}"
        )

    # graphql errors
    if "errors" in resp and resp["errors"]:
        raise RuntimeError(json.dumps(resp["errors"], indent=2))

    if "data" in resp and isinstance(resp["data"], dict) and "allGrafik" in resp["data"]:
        return resp["data"]["allGrafik"]

    raise RuntimeError("Response tidak sesuai format GraphQL allGrafik.")

def parse_json_fluktuasi_to_pricelist(js: str):
    """
    json_fluktuasi format (sesuai bukti kamu):
    - Bisa dict: {"priceList":[...], "xAxis":[...], "yAxis":[...]}
    - Bisa list wrapper: [ { ... } ]
    Yang kita ambil hanya priceList.
    """
    obj = json.loads(js)

    if isinstance(obj, list) and obj:
        obj = obj[0]

    if isinstance(obj, dict) and "priceList" in obj and isinstance(obj["priceList"], list):
        return obj["priceList"]

    raise RuntimeError("Key 'priceList' tidak ditemukan pada json_fluktuasi.")

def normalize_pricelist(pricelist: list[dict], tipe: str) -> pd.DataFrame:
    df = pd.DataFrame(pricelist)

    # kolom yang terbukti ada: lastUpdate, hargaBeli, hargaJual
    if "lastUpdate" not in df.columns:
        raise RuntimeError(f"Kolom 'lastUpdate' tidak ada. Kolom tersedia: {list(df.columns)}")

    df["tanggal"] = pd.to_datetime(df["lastUpdate"], errors="coerce")

    # harga bisa string
    if "hargaBeli" in df.columns:
        df["harga_beli"] = pd.to_numeric(df["hargaBeli"], errors="coerce")
    else:
        df["harga_beli"] = pd.NA

    if "hargaJual" in df.columns:
        df["harga_jual"] = pd.to_numeric(df["hargaJual"], errors="coerce")
    else:
        df["harga_jual"] = pd.NA

    out = df[["tanggal", "harga_beli", "harga_jual"]].sort_values("tanggal").reset_index(drop=True)

    # Optional: kalau user pilih "jual", tetap tampilkan harga_jual (harga_beli tetap ada jika tersedia)
    # Tidak perlu filter kolom.
    return out

# UI controls
c1, c2, c3 = st.columns([2, 2, 2])
with c1:
    tipe = st.selectbox("Tipe", ["beli", "jual"], index=1)
with c2:
    interval = st.number_input("time_interval (contoh: 360 = 1 tahun)", min_value=1, value=360, step=1)
with c3:
    st.caption("Catatan: token JWT bisa expired. Jika Unauthorized, update secrets.")

if st.button("📥 Ambil Data Grafik"):
    try:
        records = fetch_all_grafik()

        rec = next(
            (r for r in records
             if str(r.get("tipe", "")).lower() == tipe.lower()
             and int(r.get("time_interval", -1)) == int(interval)),
            None
        )

        if not rec:
            st.warning("Kombinasi tidak ditemukan. Ini daftar kombinasi yang tersedia:")
            combos = sorted({(str(r.get("tipe","")).lower(), int(r.get("time_interval",-1))) for r in records})
            st.write(combos)
            st.stop()

        pricelist = parse_json_fluktuasi_to_pricelist(rec["json_fluktuasi"])
        out = normalize_pricelist(pricelist, tipe)

        # basic sanity
        valid_rows = out.dropna(subset=["tanggal"]).shape[0]
        if valid_rows == 0:
            st.warning("Data berhasil diambil tapi tanggal tidak ter-parse. Cek format lastUpdate.")
        else:
            st.success(f"Berhasil! Total data: {len(out)} (valid tanggal: {valid_rows})")

        st.dataframe(out, use_container_width=True)

        st.download_button(
            "⬇️ Download CSV",
            data=out.to_csv(index=False).encode("utf-8-sig"),
            file_name=f"pegadaian_grafik_{tipe}_{interval}.csv",
            mime="text/csv",
        )

    except Exception as e:
        st.error(str(e))
