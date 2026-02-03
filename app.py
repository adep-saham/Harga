import requests
import json
import pandas as pd
import streamlit as st

GRAPHQL_URL = "https://agata.pegadaian.co.id/public/webcorp/konven/graphql"

HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "Origin": "https://pegadaian.co.id",
    "Referer": "https://pegadaian.co.id/produk/harga-emas-batangan-dan-tabungan-tabungan-emas",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120 Safari/537.36",
}

QUERY = """
query allGrafik {
  allGrafik {
    tipe
    time_interval
    json_fluktuasi
  }
}
"""

def fetch_all_grafik():
    payload = {
        "operationName": "allGrafik",
        "variables": {},
        "query": QUERY
    }
    r = requests.post(GRAPHQL_URL, headers=HEADERS, json=payload, timeout=30)
    r.raise_for_status()
    return r.json()["data"]["allGrafik"]

def parse_json_fluktuasi(js):
    obj = json.loads(js)
    if isinstance(obj, list):
        obj = obj[0]
    return obj["pricedlist"]

st.title("📈 Grafik Harga Emas Pegadaian")

data = fetch_all_grafik()

# contoh: beli 1 tahun
rec = next(x for x in data if x["tipe"] == "beli" and x["time_interval"] == 360)

priced = parse_json_fluktuasi(rec["json_fluktuasi"])
df = pd.DataFrame(priced)

df["tanggal"] = pd.to_datetime(df["lastUpdate"])
df["harga_beli"] = pd.to_numeric(df["hargaBeli"])
df["harga_jual"] = pd.to_numeric(df["hargaJual"])

df = df[["tanggal", "harga_beli", "harga_jual"]].sort_values("tanggal")

st.dataframe(df, use_container_width=True)

st.download_button(
    "⬇️ Download CSV",
    df.to_csv(index=False).encode("utf-8-sig"),
    "pegadaian_emas_1tahun.csv",
    "text/csv"
)
