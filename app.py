# app.py
# pip install streamlit requests pandas

import json
import time
import requests
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Pegadaian Grafik Emas Extractor", layout="wide")

DEFAULT_REFERER = "https://pegadaian.co.id/produk/harga-emas-batangan-dan-tabungan-tabungan-emas"

QUERY_ALL_GRAFIK = """
query allGrafik {
  allGrafik {
    id
    tipe
    time_interval
    json_fluktuasi
    updatedat
    __typename
  }
}
"""

def build_headers(extra_headers: dict | None = None) -> dict:
    # Header minimal agar request “mirip browser”
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Origin": "https://pegadaian.co.id",
        "Referer": DEFAULT_REFERER,
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
    }
    if extra_headers:
        # extra_headers boleh berisi Cookie / Authorization dll
        headers.update({k: v for k, v in extra_headers.items() if v})
    return headers

def post_graphql(url: str, headers: dict, timeout: int = 30) -> requests.Response:
    payload = {"operationName": "allGrafik", "variables": {}, "query": QUERY_ALL_GRAFIK}
    s = requests.Session()
    # retry ringan untuk 429/5xx
    for attempt in range(3):
        r = s.post(url, headers=headers, json=payload, timeout=timeout, allow_redirects=True)
        if r.status_code in (429, 500, 502, 503, 504):
            time.sleep(1.5 * (attempt + 1))
            continue
        return r
    return r

def parse_json_fluktuasi(json_fluktuasi: str):
    # json_fluktuasi sering berupa STRING JSON
    obj = json.loads(json_fluktuasi)

    # kadang dibungkus list: [{...}]
    if isinstance(obj, list) and obj:
        obj = obj[0]

    if not isinstance(obj, dict):
        raise ValueError("Struktur json_fluktuasi tidak sesuai (bukan dict/list).")

    pricedlist = obj.get("pricedlist", [])
    if not isinstance(pricedlist, list):
        raise ValueError("Struktur pricedlist tidak sesuai (bukan list).")
    return pricedlist

def to_df(pricedlist):
    df = pd.DataFrame(pricedlist)

    # normalisasi tanggal
    if "lastUpdate" in df.columns:
        df["tanggal"] = pd.to_datetime(df["lastUpdate"], errors="coerce").dt.date
    elif "tanggal" in df.columns:
        df["tanggal"] = pd.to_datetime(df["tanggal"], errors="coerce").dt.date
    else:
        df["tanggal"] = pd.NaT

    # normalisasi harga
    for src, dst in [("hargaBeli", "harga_beli"), ("hargaJual", "harga_jual")]:
        if src in df.columns:
            df[dst] = pd.to_numeric(df[src], errors="coerce")
        else:
            df[dst] = pd.NA

    out = df[["tanggal", "harga_beli", "harga_jual"]].copy()
    out = out.sort_values("tanggal").reset_index(drop=True)
    return out

st.title("📈 Pegadaian — Extract Data Angka dari Grafik")

with st.expander("⚙️ Konfigurasi", expanded=True):
    # Ambil dari secrets kalau ada
    secret_url = st.secrets.get("GRAPHQL_URL", "")
    secret_cookie = st.secrets.get("COOKIE", "")
    secret_auth = st.secrets.get("AUTHORIZATION", "")
    secret_referer = st.secrets.get("REFERER", DEFAULT_REFERER)

    graphql_url = st.text_input(
        "GraphQL URL (copy dari DevTools → Network → graphql → Headers → Request URL)",
        value=secret_url or "https://pegadaian.co.id/graphql",
    )

    referer = st.text_input("Referer", value=secret_referer)
    cookie = st.text_area("Cookie (opsional, hanya jika diperlukan)", value=secret_cookie, height=80)
    authorization = st.text_input("Authorization (opsional)", value=secret_auth)

    tipe = st.selectbox("Pilih tipe", ["beli", "jual"])
    time_interval = st.number_input("Pilih time_interval (mis. 360=1 tahun)", min_value=1, value=360, step=1)

extra_headers = {
    "Referer": referer,
    "Cookie": cookie.strip() if cookie else "",
    "Authorization": authorization.strip() if authorization else "",
}
headers = build_headers(extra_headers)

colA, colB = st.columns(2)

with colA:
    if st.button("🔌 Test Connection"):
        try:
            r = post_graphql(graphql_url, headers=headers, timeout=30)
            st.write("Status:", r.status_code)
            st.write("Final URL:", r.url)
            st.write("Response headers (subset):", {k: r.headers.get(k) for k in ["content-type", "server", "cf-ray"]})
            # tampilkan snippet supaya kelihatan error WAF/HTML/JSON
            st.code(r.text[:1500])
        except Exception as e:
            st.error(f"Test gagal: {e}")

with colB:
    st.caption("Jika status 403/406/429 atau response berisi HTML/Cloudflare, berarti diblok dari Streamlit Cloud.")

st.divider()

if st.button("📥 Ambil Data Grafik"):
    try:
        r = post_graphql(graphql_url, headers=headers, timeout=30)

        # Jangan langsung raise_for_status, tampilkan detail dulu kalau gagal
        if r.status_code != 200:
            st.error(f"HTTP {r.status_code}")
            st.code(r.text[:2000])
            st.stop()

        data = r.json()
        if "errors" in data:
            st.error("GraphQL mengembalikan errors")
            st.json(data["errors"])
            st.stop()

        records = data["data"]["allGrafik"]

        # cari record yang cocok
        chosen = None
        for rec in records:
            if str(rec.get("tipe", "")).lower() == tipe.lower() and int(rec.get("time_interval", -1)) == int(time_interval):
                chosen = rec
                break
        if not chosen:
            st.warning("Record tidak ketemu. Ini daftar kombinasi yang tersedia:")
            combos = sorted({(str(x.get("tipe")).lower(), int(x.get("time_interval"))) for x in records})
            st.write(combos)
            st.stop()

        pricedlist = parse_json_fluktuasi(chosen["json_fluktuasi"])
        df = to_df(pricedlist)

        st.success(f"Berhasil! Rows: {len(df)} | tipe={tipe} | time_interval={time_interval}")
        st.dataframe(df, use_container_width=True)

        # download csv
        csv_bytes = df.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "⬇️ Download CSV",
            data=csv_bytes,
            file_name=f"pegadaian_grafik_{tipe}_{time_interval}.csv",
            mime="text/csv",
        )

    except Exception as e:
        st.error(f"Gagal ambil data: {e}")
