#!/usr/bin/env python3
"""验证 .env 中各参数的可用性，不涉及敏感信息输出。"""

import os
import sys
import smtplib
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

# ---------- helpers ----------

def _mask(val: str, visible: int = 4) -> str:
    if not val:
        return "<空>"
    if len(val) <= visible:
        return "***"
    return val[:visible] + "***" + val[-2:]


def _status(name: str, ok: bool, detail: str = ""):
    tag = "OK" if ok else "FAIL"
    msg = f"  [{tag}] {name}"
    if detail:
        msg += f" — {detail}"
    print(msg)
    return ok


# ---------- checks ----------

def check_env_vars() -> bool:
    """检查所有必需环境变量是否已填写。"""
    print("\n=== 环境变量检查 ===")
    required = {
        "ZOTERO_ID": "Zotero 用户 ID",
        "ZOTERO_KEY": "Zotero API 密钥",
        "SENDER": "发件邮箱",
        "SENDER_PASSWORD": "SMTP 授权码",
        "RECEIVER": "收件邮箱",
        "OPENAI_API_KEY": "LLM API Key",
        "OPENAI_API_BASE": "LLM API 地址",
    }
    all_ok = True
    for var, desc in required.items():
        val = os.environ.get(var, "").strip()
        ok = bool(val)
        detail = _mask(val) if val else "未设置"
        if not _status(f"{var} ({desc})", ok, detail):
            all_ok = False
    return all_ok


def check_zotero() -> bool:
    """验证 Zotero API 连通性。"""
    print("\n=== Zotero API 检查 ===")
    uid = os.environ.get("ZOTERO_ID", "").strip()
    key = os.environ.get("ZOTERO_KEY", "").strip()
    if not uid or not key:
        _status("Zotero 连接", False, "缺少 ZOTERO_ID 或 ZOTERO_KEY")
        return False

    try:
        from pyzotero.zotero import Zotero
        zot = Zotero(uid, "user", key)
        collections = zot.collections()
        _status("Zotero 连接", True, f"成功，共 {len(collections)} 个收藏集")
        # 列出顶层收藏集名称（帮助确认 include_path 配置）
        top = [c["data"]["name"] for c in collections if "parentCollection" not in c["data"] or c["data"]["parentCollection"] is False]
        if top:
            print(f"       顶层收藏集: {', '.join(top[:10])}")
        return True
    except Exception as e:
        _status("Zotero 连接", False, str(e))
        return False


def check_smtp() -> bool:
    """验证 SMTP 连通性（不实际发信）。"""
    print("\n=== SMTP 检查 ===")
    sender = os.environ.get("SENDER", "").strip()
    pwd = os.environ.get("SENDER_PASSWORD", "").strip()
    if not sender or not pwd:
        _status("SMTP 连接", False, "缺少 SENDER 或 SENDER_PASSWORD")
        return False

    # 根据发件邮箱推断 SMTP 服务器
    smtp_map = {
        "qq.com": ("smtp.qq.com", 465),
        "gmail.com": ("smtp.gmail.com", 465),
        "outlook.com": ("smtp.office365.com", 587),
        "hotmail.com": ("smtp.office365.com", 587),
        "163.com": ("smtp.163.com", 465),
        "126.com": ("smtp.126.com", 465),
        "sina.com": ("smtp.sina.com", 465),
        "bupt.edu.cn": ("smtp.exmail.qq.com", 465),
    }
    domain = sender.split("@")[-1] if "@" in sender else ""
    server, port = smtp_map.get(domain, (None, None))

    if not server:
        # 尝试通用推断: smtp.{domain}
        server = f"smtp.{domain}"
        port = 465
        _status("SMTP 服务器推断", True, f"未在已知列表中，尝试 {server}:{port}")

    _status("SMTP 服务器推断", True, f"{server}:{port}")

    try:
        if port == 465:
            smtp = smtplib.SMTP_SSL(server, port, timeout=10)
        else:
            smtp = smtplib.SMTP(server, port, timeout=10)
            smtp.starttls()
        smtp.login(sender, pwd)
        smtp.quit()
        _status("SMTP 登录", True, "认证成功")
        return True
    except smtplib.SMTPAuthenticationError as e:
        _status("SMTP 登录", False, f"认证失败 — 请确认使用的是 SMTP 授权码而非邮箱密码 ({e})")
        return False
    except Exception as e:
        _status("SMTP 连接", False, str(e))
        return False


def check_llm() -> bool:
    """验证 LLM API 连通性。"""
    print("\n=== LLM API 检查 ===")
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    base = os.environ.get("OPENAI_API_BASE", "").strip()
    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini").strip()
    if not key or not base:
        _status("LLM API", False, "缺少 OPENAI_API_KEY 或 OPENAI_API_BASE")
        return False

    try:
        from openai import OpenAI
        client = OpenAI(api_key=key, base_url=base)
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Hi"}],
            max_tokens=5,
        )
        answer = resp.choices[0].message.content
        _status("LLM API 连接", True, f"模型 {model} 响应正常: {answer!r}")
        return True
    except Exception as e:
        err = str(e)
        if "model" in err.lower() and ("not found" in err.lower() or "does not exist" in err.lower()):
            _status("LLM API 连接", False, f"模型 {model} 不可用 — 请检查 OPENAI_MODEL 或更换模型 ({err})")
        elif "authentication" in err.lower() or "401" in err:
            _status("LLM API 连接", False, f"认证失败 — 请检查 API Key ({err})")
        else:
            _status("LLM API 连接", False, err)
        return False


def check_arxiv_categories() -> bool:
    """验证 arXiv 分类代码是否有效。"""
    print("\n=== arXiv 分类检查 ===")
    categories = [
        "eess.SP", "physics.app-ph", "physics.ins-det",
        "cs.AR", "cs.CE", "cs.ET",
        "cs.LG", "cs.AI", "cs.NE",
    ]
    try:
        import urllib.request
        import xml.etree.ElementTree as ET

        valid = []
        invalid = []
        ns = {"atom": "http://www.w3.org/2005/Atom"}

        for cat in categories:
            try:
                url = f"http://export.arxiv.org/api/query?search_query=cat:{cat}&max_results=1"
                req = urllib.request.Request(url, headers={"User-Agent": "zotero-arxiv-daily/test"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    root = ET.fromstring(resp.read())
                entries = root.findall("atom:entry", ns)
                if entries:
                    valid.append(cat)
                else:
                    invalid.append(cat)
            except Exception:
                invalid.append(cat)

        if valid:
            _status("有效分类", True, ", ".join(valid))
        if invalid:
            _status("无效分类", False, ", ".join(invalid))
        return len(invalid) == 0
    except Exception as e:
        _status("arXiv 查询", False, str(e))
        return False


# ---------- main ----------

def main():
    print("=" * 50)
    print("  Zotero-arXiv-Daily 参数验证")
    print("=" * 50)

    results = []
    results.append(("环境变量", check_env_vars()))
    results.append(("Zotero API", check_zotero()))
    results.append(("SMTP", check_smtp()))
    results.append(("LLM API", check_llm()))
    results.append(("arXiv 分类", check_arxiv_categories()))

    print("\n" + "=" * 50)
    print("  汇总")
    print("=" * 50)
    for name, ok in results:
        tag = "OK" if ok else "FAIL"
        print(f"  [{tag}] {name}")

    all_ok = all(ok for _, ok in results)
    print()
    if all_ok:
        print("所有检查通过！可以配置 GitHub Actions 运行每日推送。")
    else:
        print("部分检查未通过，请根据上方提示修正 .env 参数。")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
