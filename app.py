# -*- coding: utf-8 -*-
"""
Pegadaian Gold Chart Extractor (GraphQL allGrafik)
- Fetch GraphQL data
- Parse json_fluktuasi (double-encoded JSON)
- Export to CSV (date, harga_beli, harga_jual)

Dependencies:
  pip install requests pandas
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import requests
import pandas as pd


# 1) Set this from DevTools -> Network -> graphql -> Headers -> Request URL
GRAPHQL_URL = "https://pegadaian.co.id/graphql"  # <-- GANTI sesuai Request URL yang kamu lihat

# 2) Optional: sometimes you need headers/cookies. Start minimal first.
HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    # "User-Agent": "Mozilla/5.0 ...",  # optional
    # "Origin": "https://pegadaian.co.id",  # optional
    # "Referer": "https://pegadaian.co.id/produk/harga-emas-batangan-dan-tabungan-tabungan-emas",  # optional
    # "Cookie": "xxx=yyy; ..."  # only if API requires it
}

# GraphQL query exactly like in DevTools Payload
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


def fetch_all_grafik() -> List[Dict[str, Any]]:
    payload = {
        "operationName": "allGrafik",
        "variables": {},
        "query": QUERY_ALL_GRAFIK,
    }
    r = requests.post(GRAPHQL_URL, headers=HEADERS, json=payload, timeout=30)
    r.raise_for_status()

    data = r.json()
    if "errors" in data:
        raise RuntimeError(f"GraphQL errors: {data['errors']}")

    return data["data"]["allGrafik"]


def parse_json_fluktuasi(json_fluktuasi: str) -> List[Dict[str, Any]]:
    """
    json_fluktuasi is usually a JSON string that contains something like:
      {"pricedlist":[{"lastUpdate":"...","hargaBeli":"...","hargaJual":"..."}, ...]}
    Sometimes it's wrapped inside a list: [{"pricedlist":[...]}]
    This function returns the pricedlist array.
    """
    # First parse (turn string -> object)
    obj = json.loads(json_fluktuasi)

    # If wrapped in list, take the first element
    if isinstance(obj, list) and len(obj) > 0:
        obj = obj[0]

    if not isinstance(obj, dict):
        raise ValueError("Unexpected json_fluktuasi structure (not dict/list).")

    pricedlist = obj.get("pricedlist", [])
    if not isinstance(pricedlist, list):
        raise ValueError("Unexpected pricedlist structure (not list).")

    return pricedlist


def pick_record(records: List[Dict[str, Any]], tipe: Optional[str] = None, time_interval: Optional[int] = None) -> Dict[str, Any]:
    """
    Choose which allGrafik record to use.
    - tipe: e.g., "beli" or "jual"
    - time_interval: e.g., 360 (≈ 1 tahun)
    If not provided, it returns the first record.
    """
    if tipe is None and time_interval is None:
        return records[0]

    for rec in records:
        if tipe is not None and str(rec.get("tipe", "")).lower() != tipe.lower():
            continue
        if time_interval is not None and int(rec.get("time_interval", -1)) != int(time_interval):
            continue
        return rec

    raise ValueError(f"Record not found for tipe={tipe}, time_interval={time_interval}")


def to_dataframe(pricedlist: List[Dict[str, Any]]) -> pd.DataFrame:
    df = pd.DataFrame(pricedlist)

    # Normalize columns
    # Common keys found: lastUpdate, hargaBeli, hargaJual
    if "lastUpdate" in df.columns:
        df["tanggal"] = pd.to_datetime(df["lastUpdate"], errors="coerce").dt.date
    elif "tanggal" in df.columns:
        df["tanggal"] = pd.to_datetime(df["tanggal"], errors="coerce").dt.date
    else:
        # If date key is different, keep as-is
        df["tanggal"] = None

    # Convert prices to numeric (string -> int)
    for col_src, col_dst in [("hargaBeli", "harga_beli"), ("hargaJual", "harga_jual")]:
        if col_src in df.columns:
            df[col_dst] = pd.to_numeric(df[col_src], errors="coerce")
        else:
            df[col_dst] = pd.NA

    # Keep only essential columns (plus any you want)
    out = df[["tanggal", "harga_beli", "harga_jual"]].copy()

    # Sort by date
    out = out.sort_values("tanggal").reset_index(drop=True)
    return out


def main():
    all_grafik = fetch_all_grafik()

    # === Pilih dataset yang kamu mau ===
    # Dari screenshot kamu: tipe="beli", time_interval=360 (≈ 1 tahun)
    rec = pick_record(all_grafik, tipe="beli", time_interval=360)

    pricedlist = parse_json_fluktuasi(rec["json_fluktuasi"])
    df = to_dataframe(pricedlist)

    # Save to CSV
    csv_path = "pegadaian_grafik_emas_1tahun.csv"
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")

    # Also save to Excel
    xlsx_path = "pegadaian_grafik_emas_1tahun.xlsx"
    df.to_excel(xlsx_path, index=False)

    print("OK! Saved:")
    print(" -", csv_path)
    print(" -", xlsx_path)
    print(df.head(10))


if __name__ == "__main__":
    main()
