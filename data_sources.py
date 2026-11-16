"""统一行情数据层：优先直连（新浪/腾讯），东财作为可选补充。

背景：这台机器直连 eastmoney 被阻断、只能走 127.0.0.1:7890 代理，而代理会间断挂掉。
新浪和腾讯可以直连，所以把「全市场列表 + 日线」放到新浪，东财只用于基本面（可选）。

对外接口：
    universe()            -> DataFrame(code,name,price,pct,amount,mktcap,floatcap,pe,pb)
    kline(code, n=300)    -> DataFrame(date,open,close,high,low,volume)
    quote(codes)          -> dict(code -> {px,pct,high,low})
"""

from __future__ import annotations

import time

import pandas as pd
import requests

UA = {"User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn"}
SINA_LIST = "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData"
SINA_KLINE = "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData"
TX_QUOTE = "https://qt.gtimg.cn/q="

_session = requests.Session()
_session.trust_env = False  # 直连，避免代理挂掉时整体失效


def _get(url: str, params: dict | None = None, timeout: int = 10, tries: int = 4):
    last = None
    for i in range(tries):
        try:
            r = _session.get(url, params=params, headers=UA, timeout=timeout)
            if r.status_code == 200:
                return r
            last = f"HTTP {r.status_code}"
        except Exception as exc:  # noqa: BLE001
            last = str(exc)[:80]
        time.sleep(0.5 * (i + 1))
    raise RuntimeError(f"请求失败 {url}: {last}")


INDEX_SYMBOLS = {
    "000001": "sh000001",   # 上证指数（注意与平安银行 000001 冲突，指数必须显式指定）
    "399001": "sz399001",   # 深证成指
    "399006": "sz399006",   # 创业板指
    "000300": "sh000300",   # 沪深300
    "000688": "sh000688",   # 科创50
}


def _sym(code: str, index: bool = False) -> str:
    code = str(code).zfill(6)
    if index and code in INDEX_SYMBOLS:
        return INDEX_SYMBOLS[code]
    return ("sh" if code[0] == "6" else "sz") + code


def universe(max_pages: int = 60) -> pd.DataFrame:
    """全 A 股，按成交额降序（新浪分页，每页 100）。"""
    rows: list[dict] = []
    for page in range(1, max_pages + 1):
        try:
            r = _get(SINA_LIST, {"page": page, "num": 100, "sort": "amount", "asc": 0,
                                 "node": "hs_a", "symbol": "", "_s_r_a": "page"})
            batch = r.json()
        except Exception:
            break
        if not batch:
            break
        rows.extend(batch)
        if len(batch) < 100:
            break
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    # 去掉指数/异常行
    df = df[df["symbol"].astype(str).str.match(r"^(sh6|sz0|sz3)")]
    for col in ["trade", "changepercent", "amount", "mktcap", "nmc", "per", "pb"]:
        df[col] = pd.to_numeric(df.get(col), errors="coerce")
    df = df.rename(columns={"code": "code", "name": "name", "trade": "price",
                            "changepercent": "pct", "amount": "amount", "mktcap": "mktcap",
                            "nmc": "floatcap", "per": "pe", "pb": "pb"})
    return df.drop_duplicates(subset=["code"]).reset_index(drop=True)


def kline(code: str, n: int = 320) -> pd.DataFrame | None:
    """日线（前复权用 eastmoney 的 fqt=1；新浪这里是原始价，做均线足够）。"""
    try:
        r = _get(SINA_KLINE, {"symbol": _sym(code), "scale": 240, "ma": "no", "datalen": n})
        data = r.json()
    except Exception:
        return None
    if not data:
        return None
    df = pd.DataFrame(data)
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.rename(columns={"day": "date"}).dropna()
    return df if len(df) >= 120 else None


def kline_qfq(code: str, n: int = 900) -> pd.DataFrame | None:
    """前复权日线（腾讯）。

    注意：web.ifzq.gtimg.cn 的 fqkline 接口在被高频调用后会返回 501，
    所以优先用 proxy.finance.qq.com 的同源接口，失败再退回老接口。
    """
    sym = _sym(code)
    param = f"{sym},day,2020-01-01,2030-12-31,{n},qfq"
    urls = [
        "https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get",
        "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get",
    ]
    k = []
    for url in urls:
        try:
            r = _session.get(url, params={"param": param}, headers=UA, timeout=12)
            if r.status_code != 200:
                continue
            d = r.json()["data"][sym]
            k = d.get("qfqday") or d.get("day") or []
            if k:
                break
        except Exception:
            continue
    if not k:
        return None
    df = pd.DataFrame([row[:6] for row in k],
                      columns=["date", "open", "close", "high", "low", "volume"])
    for col in ["open", "close", "high", "low", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna()
    # 腾讯的 volume 单位是「手」（100 股），换算成股再乘价格得到近似成交额
    df["amount"] = df["volume"] * 100 * df["close"]
    time.sleep(0.03)
    return df if len(df) >= 120 else None


def quote(codes: list[str], index: bool = False) -> dict:
    """腾讯实时报价（盘中用）：code -> {px,pct,high,low}。index=True 时按指数映射。"""
    out = {}
    for i in range(0, len(codes), 20):
        chunk = codes[i:i + 20]
        try:
            r = _session.get(TX_QUOTE + ",".join(_sym(c, index) for c in chunk), headers=UA, timeout=8)
            r.encoding = "gbk"
        except Exception:
            continue
        for line in r.text.strip().split("\n"):
            if "=" not in line:
                continue
            f = line.split("=", 1)[1].strip().strip(";").strip('"').split("~")
            if len(f) < 35:
                continue
            try:
                cur, prev = float(f[3]), float(f[4])
                out[f[2]] = {"px": cur, "pct": (cur / prev - 1) * 100,
                             "high": float(f[33]), "low": float(f[34])}
            except Exception:
                continue
    return out
