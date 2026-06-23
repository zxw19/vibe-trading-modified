"""Read-only CNINFO (巨潮资讯) official disclosure-announcement search tool.

CNINFO (www.cninfo.com.cn) is the CSRC-designated information disclosure
platform for all China A-share listed companies. Every official filing —
annual/quarterly reports, IPO prospectuses, material-asset restructurings,
shareholder-meeting notices, exchange inquiry letters, and delisting-risk
warnings — is published here as the authoritative primary source.

This tool wraps CNINFO's free, no-auth ``hisAnnouncement/query`` JSON API
behind the project's BaseTool contract and the shared IP-throttled HTTP
layer (CNINFO rate-limits by source IP), so the agent never hits the host
un-throttled and never re-implements provider plumbing.

Markets: mainland A-shares only (.SH / .SZ / .BJ). The exchange suffix is
mapped to the ``column`` parameter (``sse`` for Shanghai, ``szse`` for
Shenzhen / Beijing).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from backtest.loaders._http import (
    DEFAULT_USER_AGENT,
    resolve_min_interval,
    throttled_post_json,
)
from src.agent.tools import BaseTool

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# CNINFO API
# ---------------------------------------------------------------------------

_CNINFO_QUERY_URL = "http://www.cninfo.com.cn/new/hisAnnouncement/query"

_CNINFO_HOST_KEY = "cninfo"
_CNINFO_MIN_INTERVAL_ENV = "VIBE_TRADING_CNINFO_MIN_INTERVAL"
_CNINFO_DEFAULT_MIN_INTERVAL = 1.0

# Hard caps so a long history cannot bloat the LLM context.
_DEFAULT_PAGE_SIZE = 20
_MAX_PAGE_SIZE = 30
# CNINFO's API returns ~30 announcements per page sorted by date DESC
# across ALL stocks (the stock filter is non-functional on the server side).
# We client-side filter by secCode.  For a stock that files infrequently
# (e.g. Moutai files 4-6 times/year), its latest filing could be buried
# behind many pages of more-active stocks.  10 pages (300 announcements)
# covers roughly 1-3 calendar days of all-market filings; combine with
# ``seDate`` for older periods.
_MAX_PAGES = 10
_MAX_TOTAL = _MAX_PAGE_SIZE * _MAX_PAGES  # 300

# A-share suffix -> CNINFO column
_SUFFIX_TO_COLUMN: dict[str, str] = {
    "SH": "sse",
    "SZ": "szse",
    "BJ": "szse",  # Beijing exchange shares the SZSE column
}

# Common announcement categories the agent may search for.
_KNOWN_CATEGORIES: dict[str, str] = {
    "年报": "category_ndbg_szsh",
    "年度报告": "category_ndbg_szsh",
    "半年报": "category_bndbg_szsh",
    "半年度报告": "category_bndbg_szsh",
    "一季报": "category_yjdbg_szsh",
    "三季报": "category_sndbg_szsh",
    "季度报告": "",
    "IPO": "category_IPO_szsh",
    "招股书": "category_IPO_szsh",
    "权益分派": "category_qyfp_szsh",
    "分红": "category_qyfp_szsh",
    "股东大会": "category_gddh_szsh",
    "重大资产重组": "category_zdzczz_szsh",
    "关联交易": "category_gljy_szsh",
    "问询函": "category_wxh_szsh",
    "监管函": "category_jgh_szsh",
    "日常经营": "category_rcjy_szsh",
    "退市风险": "category_tsfx_szsh",
}


def _cninfo_min_interval() -> float:
    return resolve_min_interval(_CNINFO_MIN_INTERVAL_ENV, _CNINFO_DEFAULT_MIN_INTERVAL)


def _bare_code(code: str) -> str:
    """Strip exchange suffix, keeping only the numeric ticker."""
    return code.strip().split(".", 1)[0].strip()


def _column_for(code: str) -> str | None:
    """Map an A-share suffix to the CNINFO ``column`` parameter."""
    suffix = code.rpartition(".")[2].strip().upper()
    return _SUFFIX_TO_COLUMN.get(suffix)


def _category_for(searchkey: str) -> str:
    """Map a Chinese keyword to a CNINFO ``category`` filter value."""
    return _KNOWN_CATEGORIES.get(searchkey, "")


def _clamp_page_size(raw: Any) -> int:
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return _DEFAULT_PAGE_SIZE
    return max(1, min(n, _MAX_PAGE_SIZE))


def _fetch_page(
    code: str,
    column: str,
    searchkey: str,
    start_date: str,
    end_date: str,
    page_num: int,
    page_size: int,
) -> dict[str, Any]:
    """Fetch one page of announcements from CNINFO.

    Returns the decoded JSON payload.  The CNINFO API currently ignores the
    ``stock`` filter parameter (returns all recent announcements regardless),
    so *filtering is done client-side* in the caller.
    """
    se_date = f"{start_date}~{end_date}" if start_date and end_date else ""
    body = {
        "pageNum": page_num,
        "pageSize": page_size,
        "column": column,
        "tabName": "fulltext",
        "plate": "",
        "stock": _bare_code(code),
        "searchkey": searchkey,
        "secid": "",
        "category": _category_for(searchkey),
        "trade": "",
        "seDate": se_date,
        "sortName": "",
        "sortType": "desc",
        "isHLtitle": "true",
    }
    return throttled_post_json(
        _CNINFO_QUERY_URL,
        host_key=_CNINFO_HOST_KEY,
        min_interval=_cninfo_min_interval(),
        json_body=body,
        headers={
            "User-Agent": DEFAULT_USER_AGENT,
            "Referer": "http://www.cninfo.com.cn/",
            "Content-Type": "application/json;charset=UTF-8",
            "Accept": "application/json",
        },
        timeout=20.0,
    )


def _normalize_announcement(raw: dict[str, Any]) -> dict[str, Any]:
    """Project one raw CNINFO row into a compact record."""
    adjunct = raw.get("adjunctUrl") or ""
    if adjunct and not adjunct.startswith("http"):
        adjunct = f"http://static.cninfo.com.cn/{adjunct}"
    return {
        "id": raw.get("announcementId"),
        "title": raw.get("announcementTitle"),
        "published": _clean_date(raw.get("announcementTime")),
        "sec_code": raw.get("secCode"),
        "sec_name": raw.get("secName"),
        "file_url": adjunct,
        "file_size": raw.get("adjunctSize"),
    }


def _clean_date(value: Any) -> str | None:
    """Convert a CNINFO millisecond timestamp to ``YYYY-MM-DD``."""
    if value is None:
        return None
    try:
        ms = int(value)
        import datetime
        return datetime.datetime.fromtimestamp(ms / 1000).strftime("%Y-%m-%d")
    except (TypeError, ValueError, OSError):
        return str(value)[:10] if isinstance(value, str) else None


def _flatten_announcements(payload: Any) -> list[dict[str, Any]]:
    """Extract announcement rows from a CNINFO query payload.

    CNINFO nests rows under ``classifiedAnnouncements`` (a dict of
    category -> list) or under ``announcements`` (a plain list).
    """
    if not isinstance(payload, dict):
        return []
    rows = payload.get("classifiedAnnouncements") or payload.get("announcements")
    if rows is None:
        return []
    if isinstance(rows, list):
        return [_normalize_announcement(r) for r in rows if isinstance(r, dict)]
    if isinstance(rows, dict):
        flat: list[dict[str, Any]] = []
        for category_items in rows.values():
            if isinstance(category_items, list):
                flat.extend(category_items)
        return [_normalize_announcement(r) for r in flat if isinstance(r, dict)]
    return []


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------


class CninfoAnnouncementsTool(BaseTool):
    """Search authoritative A-share company announcements from CNINFO."""

    name = "get_cninfo_announcements"
    description = (
        "Search official A-share company announcements (公告) from CNINFO "
        "(巨潮资讯网), the CSRC-designated disclosure platform. Returns "
        "authoritative primary-source filings: annual/quarterly reports, "
        "prospectuses, material announcements, inquiry letters, shareholder "
        "meeting notices, and more. Use this as the FIRST stop for any factual "
        "claim about a company — CNINFO is more authoritative than broker "
        "reports or news.\n\n"
        "TIP: For infrequent filers, specify start_date/end_date to narrow "
        "the search window (e.g. start_date='2026-03-01' for Q1 filings).\n\n"
        "Markets: China A-shares only (.SH / .SZ / .BJ). "
        'Example: get_cninfo_announcements(code="600519.SH", searchkey="年报", '
        'start_date="2025-01-01", end_date="2025-12-31").'
    )
    parameters = {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": (
                    "A-share symbol with exchange suffix, e.g. '600519.SH', "
                    "'000001.SZ', '830799.BJ'."
                ),
            },
            "searchkey": {
                "type": "string",
                "description": (
                    "Chinese search keyword, e.g. '年报', '季报', '招股', "
                    "'问询函', '分红', '资产重组', '退市'. Leave empty for all "
                    "announcements."
                ),
                "default": "",
            },
            "start_date": {
                "type": "string",
                "description": "Start date in YYYY-MM-DD format.",
            },
            "end_date": {
                "type": "string",
                "description": "End date in YYYY-MM-DD format.",
            },
            "page_size": {
                "type": "integer",
                "description": (
                    "Results per page (1-30). Default 20, max 30. "
                    "Up to 5 pages are fetched automatically."
                ),
                "default": _DEFAULT_PAGE_SIZE,
            },
        },
        "required": ["code"],
    }

    def execute(self, **kwargs: Any) -> str:
        """Query CNINFO announcements for one A-share code.

        CNINFO's ``hisAnnouncement/query`` API currently ignores the ``stock``
        filter parameter, so filtering is done client-side: pages are fetched
        (newest-first) and rows whose ``secCode`` matches the requested code
        are collected.  We stop when the requested number of matching rows is
        reached or ``_MAX_PAGES`` have been scanned.

        Args:
            **kwargs: ``code`` (required A-share symbol), ``searchkey``
                (optional keyword), ``start_date`` / ``end_date`` (optional
                date range), ``page_size`` (1-30).

        Returns:
            A JSON string envelope.
        """
        code = kwargs.get("code")
        if not isinstance(code, str) or not code.strip():
            return _error("'code' is required and must be a non-empty A-share symbol")
        code = code.strip().upper()

        column = _column_for(code)
        if column is None:
            return _error(
                f"CNINFO supports A-shares only (.SH/.SZ/.BJ); got '{code}'"
            )

        searchkey = str(kwargs.get("searchkey") or "")
        start_date = str(kwargs.get("start_date") or "")
        end_date = str(kwargs.get("end_date") or "")
        page_size = _clamp_page_size(kwargs.get("page_size", _DEFAULT_PAGE_SIZE))

        bare = _bare_code(code)
        matched: list[dict[str, Any]] = []
        total_available = 0

        for page in range(1, _MAX_PAGES + 1):
            try:
                payload = _fetch_page(
                    code, column, searchkey, start_date, end_date, page, page_size
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("cninfo fetch failed (page %s): %s", page, exc)
                if page == 1:
                    return _error(f"CNINFO request failed: {exc}")
                break  # later-page failure: return what we have

            rows = _flatten_announcements(payload)
            if total_available == 0:
                total_available = payload.get("totalRecordNum") or payload.get("totalRecords") or 0

            # Client-side filter: CNINFO ignores the stock param, so we match
            # on secCode ourselves.
            for row in rows:
                if row.get("sec_code") == bare:
                    matched.append(row)

            # Stop scanning more pages when we have enough matches or the API
            # returned fewer rows than requested (last page).
            if len(rows) < page_size:
                break
            if len(matched) >= page_size:
                break

        if not matched:
            return _error(
                f"no announcements found for '{code}'"
                + (f" with searchkey '{searchkey}'" if searchkey else "")
            )

        return json.dumps(
            {
                "ok": True,
                "market": "a_share",
                "source": "cninfo",
                "data": {
                    "code": code,
                    "searchkey": searchkey,
                    "date_range": f"{start_date}~{end_date}",
                    "count": len(matched),
                    "scanned_pages": page,
                    "total_indexed": total_available,
                    "announcements": matched[:_MAX_TOTAL],
                },
            },
            ensure_ascii=False,
        )


def _error(message: str) -> str:
    return json.dumps({"ok": False, "error": message}, ensure_ascii=False)
