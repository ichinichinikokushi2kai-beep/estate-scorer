"""
新着物件のメール送信。本文に新着一覧と「全物件一覧」リンクを含める。
"""
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def send_new_listings_email(
    new_listings: List[Dict[str, Any]],
    list_page_url: Optional[str],
    *,
    smtp_host: str,
    smtp_port: int,
    smtp_user: str,
    smtp_pass: str,
    from_email: str,
    to_emails: List[str],
) -> bool:
    """
    新着一覧と全物件一覧リンクを含むメールを送信する。
    to_emails はアドレス文字列のリスト。
    """
    if not new_listings:
        return True
    if not to_emails:
        logger.warning("送信先メールアドレスが設定されていません")
        return False

    subject = f"【SUUMO】新着物件 {len(new_listings)} 件"
    body = _build_body(new_listings, list_page_url)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = ", ".join(to_emails)

    msg.attach(MIMEText(body, "plain", "utf-8"))

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(from_email, to_emails, msg.as_string())
        logger.info("メール送信完了: %s 件の新着を %s 宛に送信", len(new_listings), to_emails)
        return True
    except Exception as e:
        logger.exception("メール送信に失敗しました: %s", e)
        return False


def _build_body(new_listings: List[Dict[str, Any]], list_page_url: Optional[str]) -> str:
    lines = [
        f"新着物件が {len(new_listings)} 件あります。",
        "",
        "【新着一覧】",
        "-" * 50,
    ]
    for r in new_listings:
        name = r.get("property_name") or "(物件名なし)"
        url = r.get("property_url") or ""
        price = _format_price(r)
        addr = (r.get("address") or "")[:40]
        lines.append(f"・ {name}")
        lines.append(f"  価格: {price}  住所: {addr}")
        if url:
            lines.append(f"  {url}")
        lines.append("")
    lines.append("-" * 50)
    if list_page_url:
        lines.append("")
        lines.append("【全物件一覧（条件ポイント降順）】")
        lines.append(list_page_url)
    return "\n".join(lines)


def _format_price(r: Dict[str, Any]) -> str:
    pmin = r.get("price_min")
    pmax = r.get("price_max")
    if pmin is not None and pmax is not None:
        if pmin == pmax:
            return f"{pmin}万円"
        return f"{pmin}～{pmax}万円"
    if pmin is not None:
        return f"{pmin}万円～"
    if pmax is not None:
        return f"～{pmax}万円"
    return ""
