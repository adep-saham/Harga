import json
import requests
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Grafik Harga Emas Pegadaian", layout="wide")
st.title("📈 Grafik Harga Emas Pegadaian")

GRAPHQL_URL = "https://agata.pegadaian.co.id/public/webcorp/konven/graphql"
REFERER = "https://pegadaian.co.id/produk/harga-emas-batangan-dan-tabungan-tabungan-emas"

HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "Origin": "https://pegadaian.co.id",
    "Referer": REFERER,
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120 Safari/537.36",
}

QUERY = """
query allGrafik {
  allGrafik {
    tipe
    time_interval
    json_fluktuasi
    updatedat
  }
}
"""

def fetch_all_grafik():
    payload = {"operationName": "allGrafik", "variables": {}, "query": QUERY}
    r = requests.post(GRAPHQL_URL, headers=HEADERS, json=payload, timeout=30)

    # Debug friendly checks
    ct = (r.headers.get("content-type") or "").lower()
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}\n\n{r.text[:1500]}")
    if "application/json" not in ct:
        raise RuntimeError(f"Unexpected content-type: {ct}\n\n{r.text[:1500]}")

    data = r.json()

    # GraphQL errors (kalau ada)
    if "errors" in data and data["errors"]:
        raise RuntimeError(f"GraphQL errors:\n{json.dumps(data['errors'], indent=2)[:1500]}")

    # ✅ Case-sensitive key: allGrafik
    try:
        return data["data"]["allGrafik"]
    except Exception:
        raise RuntimeError("Key data['data']['allGrafik'] tidak ditemukan.\n\n"
                           f"Response keys: {list(data.keys())}\n\n"
                           f"Full JSON (truncated): {json.dumps(data, indent=2)[:1500]}")

def parse_json_fluktuasi(js: str):
    obj = json.loads(js)
    if isinstance(obj, list) and obj:
        obj = obj[0]
    pricedlist = obj.get("pricedlist", [])
    return pricedlist

# UI pilih tipe & interval
tipe = st.selectbox("Tipe", ["beli", "jual"], index=0)
interval = st.number_input("time_interval (contoh 360 = 1 tahun)", min_value=1, value=360, step=1)

try:
    records = fetch_all_grafik()

    # cari record yang cocok
    rec = next((x for x in records if str(x.get("tipe","")).lower() == tipe and int(x.get("time_interval", -1)) == int(interval)), None)

    if not rec:
        st.warning("Kombinasi tidak ditemukan. Ini daftar yang tersedia:")
        combos = sorted({(str(x.get("tipe","")).lower(), int(x.get("time_interval",-1))) for x in records})
        st.write(combos)
        st.stop()

    priced = parse_json_fluktuasi(rec["json_fluktuasi"])
    df = pd.DataFrame(priced)

    # normalisasi kolom
    df["tanggal"] = pd.to_datetime(df.get("lastUpdate"), errors="coerce")
    df["harga_beli"] = pd.to_numeric(df.get("hargaBeli"), errors="coerce")
    df["harga_jual"] = pd.to_numeric(df.get("hargaJual"), errors="coerce")

    out = df[["tanggal", "harga_beli", "harga_jual"]].sort_values("tanggal").reset_index(drop=True)

    st.success(f"Berhasil! Rows: {len(out)} | tipe={tipe} | interval={interval}")
    st.dataframe(out, use_container_width=True)

    st.download_button(
        "⬇️ Download CSV",
        out.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"pegadaian_grafik_{tipe}_{interval}.csv",
        mime="text/csv",
    )

except Exception as e:
    st.error(str(e))
