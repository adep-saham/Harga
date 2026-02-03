# app.py
# =========================================
# Grafik Harga Emas Pegadaian (GraphQL)
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

# -------------------------------
# PAGE CONFIG
# -------------------------------
st.set_page_config(
    page_title="Grafik Harga Emas Pegadaian",
    layout="wide",
)

st.title("📈 Grafik Harga Emas Pegadaian")

# -------------------------------
# CONSTANTS
# -------------------------------
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

# -------------------------------
# HEADERS
# -------------------------------
def build_headers():
    apikey = st.secrets.get("PEGADAIAN_APIKEY", "")
    bearer = st.secrets.get("PEGADAIAN_BEARER", "")

    if not apikey or not bearer:
        raise RuntimeError(
            "Secrets belum lengkap.\n"
            "Isi PEGADAIAN_APIKEY dan PEGADAIAN_BEARER di Streamlit Secrets."
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
        # 🔑 WAJIB
        "apikey": apikey,
        "authorization": f"Bearer {bearer}",
    }

# -------------------------------
# FETCH GRAPHQL
# -------------------------------
def fetch_all_grafik():
    headers = build_headers()
    payload = {
        "operationName": "allGrafik",
        "variables": {},
        "query": QUERY_ALL_GRAFIK,
    }

    r = requests.post(
        GRAPHQL_URL,
        headers=headers,
        json=payload,
        timeout=30,
    )

    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}\n\n{r.text[:1500]}")

    resp = r.json()

    # ❌ Unauthorized / wrapper error
    if resp.get("responseCode") and resp.get("data") is None:
        raise RuntimeError(
            f"Unauthorized / Invalid Token\n"
            f"responseCode={resp.get('responseCode')}\n"
            f"responseDesc={resp.get('responseDesc')}"
        )

    # ❌ GraphQL error
    if "errors" in resp:
        raise RuntimeError(f"GraphQL errors:\n{json.dumps(resp['errors'], indent=2)}")

    # ✅ Normal GraphQL
    if "data" in resp and "allGrafik" in resp["data"]:
        return resp["data"]["allGrafik"]

    raise RuntimeError(
        "Struktur response tidak dikenali:\n"
        + json.dumps(resp, indent=2)[:1500]
    )

# -------------------------------
# PARSE json_fluktuasi (DOUBLE JSON)
# -------------------------------
def parse_json_fluktuasi(js: str):
    obj = json.loads(js)

    # kadang dibungkus list
    if isinstance(obj, list) and obj:
        obj = obj[0]

    if not isinstance(obj, dict) or "pricedlist" not in obj:
        raise RuntimeError("Format json_fluktuasi tidak sesuai.")

    return obj["pricedlist"]

# -------------------------------
# UI CONTROLS
# -------------------------------
col1, col2 = st.columns(2)

with col1:
    tipe = st.selectbox("Tipe", ["beli", "jual"], index=0)

with col2:
    interval = st.number_input(
        "time_interval (contoh: 360 = 1 tahun)",
        min_value=1,
        value=360,
        step=1,
    )

# -------------------------------
# MAIN ACTION
# -------------------------------
if st.button("📥 Ambil Data Grafik"):
    try:
        records = fetch_all_grafik()

        # cari record sesuai pilihan
        record = next(
            (
                r for r in records
                if str(r.get("tipe", "")).lower() == tipe
                and int(r.get("time_interval", -1)) == int(interval)
            ),
            None,
        )

        if not record:
            st.warning("Data tidak ditemukan untuk kombinasi ini.")
            st.write(
                sorted(
                    {
                        (str(r.get("tipe", "")).lower(), int(r.get("time_interval", -1)))
                        for r in records
                    }
                )
            )
            st.stop()

        priced = parse_json_fluktuasi(record["json_fluktuasi"])
        df = pd.DataFrame(priced)

        # normalisasi kolom
        df["tanggal"] = pd.to_datetime(df.get("lastUpdate"), errors="coerce")
        df["harga_beli"] = pd.to_numeric(df.get("hargaBeli"), errors="coerce")
        df["harga_jual"] = pd.to_numeric(df.get("hargaJual"), errors="coerce")

        out = (
            df[["tanggal", "harga_beli", "harga_jual"]]
            .sort_values("tanggal")
            .reset_index(drop=True)
        )

        st.success(f"Berhasil! Total data: {len(out)}")
        st.dataframe(out, use_container_width=True)

        # download CSV
        st.download_button(
            "⬇️ Download CSV",
            data=out.to_csv(index=False).encode("utf-8-sig"),
            file_name=f"pegadaian_grafik_{tipe}_{interval}.csv",
            mime="text/csv",
        )

    except Exception as e:
        st.error(str(e))

