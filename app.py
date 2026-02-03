# app.py
# =========================================
# Grafik Harga Emas Pegadaian (FINAL)
# + Download CSV & Excel
# =========================================
# Requirements:
#   pip install streamlit requests pandas openpyxl
#
# Streamlit Secrets (WAJIB):
#   PEGADAIAN_APIKEY = "apikey dari DevTools"
#   PEGADAIAN_BEARER = "JWT token TANPA kata Bearer"
# =========================================

import json
import requests
import pandas as pd
import streamlit as st
from io import BytesIO

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

    if "errors" in resp and resp["errors"]:
        raise RuntimeError(json.dumps(resp["errors"], indent=2))

    if "data" in resp and isinstance(resp["data"], dict) and "allGrafik" in resp["data"]:
        return resp["data"]["allGrafik"]

    raise RuntimeError("Response tidak sesuai format GraphQL allGrafik.")

def parse_json_fluktuasi_to_pricelist(js: str):
    obj = json.loads(js)

    if isinstance(obj, list) and obj:
        obj = obj[0]

    if isinstance(obj, dict) and "priceList" in obj and isinstance(obj["priceList"], list):
        return obj["priceList"]

    raise RuntimeError("Key 'priceList' tidak ditemukan pada json_fluktuasi.")

def normalize_pricelist(pricelist: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(pricelist)

    if "lastUpdate" not in df.columns:
        raise RuntimeError(f"Kolom 'lastUpdate' tidak ada. Kolom tersedia: {list(df.columns)}")

    df["tanggal"] = pd.to_datetime(df["lastUpdate"], errors="coerce")
    df["harga_beli"] = pd.to_numeric(df.get("hargaBeli"), errors="coerce")
    df["harga_jual"] = pd.to_numeric(df.get("hargaJual"), errors="coerce")

    out = (
        df[["tanggal", "harga_beli", "harga_jual"]]
        .sort_values("tanggal")
        .reset_index(drop=True)
    )
    return out

def to_excel_bytes(df: pd.DataFrame, sheet_name: str = "data") -> bytes:
    buf = BytesIO()
    # openpyxl is the default engine for .xlsx
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)

        # Optional: autosize columns (simple)
        ws = writer.sheets[sheet_name]
        for idx, col in enumerate(df.columns, start=1):
            max_len = max([len(str(col))] + [len(str(x)) for x in df[col].astype(str).head(200)])
            ws.column_dimensions[chr(64 + idx)].width = min(max_len + 2, 40)

    buf.seek(0)
    return buf.getvalue()

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
        out = normalize_pricelist(pricelist)

        valid_rows = out.dropna(subset=["tanggal"]).shape[0]
        st.success(f"Berhasil! Total data: {len(out)} (valid tanggal: {valid_rows})")
        st.dataframe(out, use_container_width=True)

        # Download buttons
        colA, colB = st.columns(2)

        with colA:
            st.download_button(
                "⬇️ Download CSV",
                data=out.to_csv(index=False).encode("utf-8-sig"),
                file_name=f"pegadaian_grafik_{tipe}_{interval}.csv",
                mime="text/csv",
            )

        with colB:
            xlsx_bytes = to_excel_bytes(out, sheet_name=f"{tipe}_{interval}")
            st.download_button(
                "⬇️ Download Excel",
                data=xlsx_bytes,
                file_name=f"pegadaian_grafik_{tipe}_{interval}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

    except Exception as e:
        st.error(str(e))
