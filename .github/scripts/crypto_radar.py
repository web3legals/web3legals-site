#!/usr/bin/env python3
"""
crypto_radar.py — Web3Legals Auto-Publishing Blog System
Phase 1: Hybrid Cloudflare Architecture

Flow:
  1. Fetch 11 Google News RSS feeds
  2. Check Cloudflare D1 (via Worker) → filter already-seen articles
  3. Generate 400-word legal analysis via Cloudflare AI Gateway → Groq LLaMA 3.3 70B
  4. Fallback chain: Groq → Gemini → structured snippet
  5. Save article HTML to blog/
  6. Rebuild blog/index.html (fully static)
  7. Write metadata back to D1
  8. git commit + push → Cloudflare Pages auto-deploys
"""

import os
import json
import time
import hashlib
import re
import textwrap
from datetime import datetime, timezone
from urllib.request import urlopen, Request
from urllib.error import URLError
import urllib.parse
import xml.etree.ElementTree as ET

# ── Environment variables (all from GitHub Secrets) ──────────────────────────

GROQ_API_KEY      = os.environ.get("GROQ_API_KEY", "")
CF_AI_GATEWAY_URL = os.environ.get("CF_AI_GATEWAY_URL", "").rstrip("/")
CF_WORKER_URL     = os.environ.get("CF_WORKER_URL", "").rstrip("/")
CF_WORKER_SECRET  = os.environ.get("CF_WORKER_SECRET", "")

# ── Config ────────────────────────────────────────────────────────────────────

MAX_ARTICLES   = 5
DELAY_SECONDS  = 5      # between Groq calls
MAX_RETRIES    = 3
BLOG_DIR       = "blog"

GROQ_MODEL     = "llama-3.3-70b-versatile"
GEMINI_MODEL   = "gemini-2.0-flash-lite"   # fallback only

RSS_FEEDS = [
    ("crypto",      "https://news.google.com/rss/search?q=crypto+regulation+law&hl=en-US&gl=US&ceid=US:en"),
    ("crypto",      "https://news.google.com/rss/search?q=cryptocurrency+SEC+CFTC&hl=en-US&gl=US&ceid=US:en"),
    ("crypto",      "https://news.google.com/rss/search?q=MiCA+DeFi+compliance&hl=en-US&gl=US&ceid=US:en"),
    ("crypto",      "https://news.google.com/rss/search?q=blockchain+legal+court+ruling&hl=en-US&gl=US&ceid=US:en"),
    ("compliance",  "https://news.google.com/rss/search?q=crypto+AML+KYC+FATF&hl=en-US&gl=US&ceid=US:en"),
    ("dao",         "https://news.google.com/rss/search?q=DAO+token+securities+law&hl=en-US&gl=US&ceid=US:en"),
    ("fintech",     "https://news.google.com/rss/search?q=fintech+regulation+RBI+legal&hl=en-IN&gl=IN&ceid=IN:en"),
    ("india-legal", "https://news.google.com/rss/search?q=India+Supreme+Court+ruling+2026&hl=en-IN&gl=IN&ceid=IN:en"),
    ("india-legal", "https://news.google.com/rss/search?q=India+High+Court+judgment+2026&hl=en-IN&gl=IN&ceid=IN:en"),
    ("fintech",     "https://news.google.com/rss/search?q=RBI+SEBI+regulation+India+2026&hl=en-IN&gl=IN&ceid=IN:en"),
    ("fintech",     "https://news.google.com/rss/search?q=India+fintech+law+digital+payment&hl=en-IN&gl=IN&ceid=IN:en"),
]

CATEGORY_META = {
    "crypto":      {"label": "Crypto Law",      "emoji": "⚖️",  "badge": "CRYPTO"},
    "fintech":     {"label": "Fintech",          "emoji": "🏦",  "badge": "FINTECH"},
    "india-legal": {"label": "India Courts",     "emoji": "🏛️",  "badge": "INDIA"},
    "compliance":  {"label": "Compliance",       "emoji": "🔍",  "badge": "AML/KYC"},
    "dao":         {"label": "DAO & Governance", "emoji": "🗳️",  "badge": "DAO"},
    "token":       {"label": "Token Law",        "emoji": "🪙",  "badge": "TOKEN"},
}

# ── Utilities ─────────────────────────────────────────────────────────────────

def article_id(url):
    return hashlib.md5(url.encode()).hexdigest()[:12]

def slugify(title):
    slug = re.sub(r"[^\w\s-]", "", title.lower())
    slug = re.sub(r"[\s_]+", "-", slug).strip("-")
    return slug[:80]

def format_display_date(pubdate_str):
    for fmt in [
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S GMT",
        "%a, %d %b %Y %H:%M:%S +0000",
    ]:
        try:
            dt = datetime.strptime(pubdate_str.strip(), fmt)
            return dt.strftime("%B %d, %Y")
        except Exception:
            continue
    return datetime.now(timezone.utc).strftime("%B %d, %Y")

# ── Cloudflare D1 Bridge calls ────────────────────────────────────────────────

def worker_request(method, path, body=None):
    """Make an authenticated request to the Cloudflare Worker D1 bridge."""
    url  = f"{CF_WORKER_URL}{path}"
    data = json.dumps(body).encode() if body else None
    req  = Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {CF_WORKER_SECRET}",
            "Content-Type":  "application/json",
        },
    )
    try:
        with urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        print(f"  Worker error [{method} {path}]: {e}")
        return None

def d1_check_seen(aids):
    """Returns set of AIDs already in D1."""
    result = worker_request("POST", "/seen/check", {"aids": aids})
    if result and "seen" in result:
        return set(result["seen"])
    print("  D1 check failed — treating all as unseen (safe fallback)")
    return set()

def d1_mark_seen(aids):
    """Mark a list of AIDs as seen in D1."""
    result = worker_request("POST", "/seen/add", {"aids": aids})
    if result:
        print(f"  D1: marked {result.get('added', 0)} articles as seen")
    else:
        print("  D1 mark-seen failed (non-critical)")

def d1_upsert_articles(articles):
    """Write article metadata to D1."""
    result = worker_request("POST", "/articles/upsert", {"articles": articles})
    if result:
        print(f"  D1: upserted {result.get('upserted', 0)} articles")
    else:
        print("  D1 upsert failed (non-critical — HTML already saved)")

def d1_get_all_articles():
    """Fetch all article metadata from D1 for index rebuild."""
    result = worker_request("GET", "/articles?limit=500", None)
    if result and "articles" in result:
        return result["articles"]
    print("  D1 fetch failed — falling back to local .all_articles.json")
    # Fallback to local file if D1 is unreachable
    if os.path.exists(".all_articles.json"):
        with open(".all_articles.json") as f:
            return json.load(f)
    return []

# ── RSS Fetching ──────────────────────────────────────────────────────────────

def fetch_rss(url, category):
    items = []
    try:
        req = Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; Web3Legals/1.0)"},
        )
        with urlopen(req, timeout=15) as resp:
            xml_data = resp.read()
        root    = ET.fromstring(xml_data)
        channel = root.find("channel")
        if channel is None:
            return items
        for item in channel.findall("item"):
            title_el   = item.find("title")
            link_el    = item.find("link")
            desc_el    = item.find("description")
            pubdate_el = item.find("pubDate")
            if title_el is None or link_el is None:
                continue
            title   = (title_el.text or "").strip()
            link    = (link_el.text or "").strip()
            snippet = re.sub(
                r"<[^>]+>",
                "",
                (desc_el.text or "") if desc_el is not None else "",
            ).strip()
            pubdate = (pubdate_el.text or "").strip() if pubdate_el is not None else ""
            if len(title) < 10:
                continue
            items.append({
                "title":    title,
                "url":      link,
                "snippet":  snippet[:400],
                "pubdate":  pubdate,
                "category": category,
            })
    except Exception as e:
        print(f"  RSS error ({url[:60]}): {e}")
    return items

def fetch_article_text(url):
    """Try full article text via newspaper3k; silent fail."""
    try:
        from newspaper import Article
        art = Article(url)
        art.download()
        art.parse()
        text = (art.text or "").strip()
        return text[:3000] if text else ""
    except Exception:
        return ""

# ── AI Generation via Cloudflare AI Gateway ───────────────────────────────────

def build_prompt(title, snippet, article_text, category):
    cat_label = CATEGORY_META.get(category, {}).get("label", category)
    context   = article_text if article_text else snippet
    return textwrap.dedent(f"""
        You are Rahul Pareek, founder of Web3Legals and a Double Gold Medallist LLM
        from National Law University India. You are India's leading expert in crypto law,
        fintech regulation, and Indian judiciary matters.

        Write a 400-word original legal analysis of the following news for Web3Legals.com.
        Category: {cat_label}

        News Title: {title}

        Context:
        {context}

        Requirements:
        - Write in first person as Rahul Pareek
        - Open with a sharp, specific legal observation — not a generic intro
        - Cite relevant laws, regulations, or court precedents where applicable
          (SEC, CFTC, MiCA, RBI, SEBI, IPC, Indian IT Act, PMLA, FEMA, etc.)
        - Explain practical implications for founders, investors, and compliance teams
        - End with a concrete takeaway or recommended action
        - Exactly 400 words
        - Plain paragraphs only — no markdown, no bullets, no headers
        - Do NOT repeat the news title verbatim in the first sentence
    """).strip()

def call_groq_via_gateway(prompt):
    """
    Call Groq LLaMA 3.3 70B through Cloudflare AI Gateway.
    Gateway URL format: https://gateway.ai.cloudflare.com/v1/{account_id}/{gateway_name}/groq
    """
    if not CF_AI_GATEWAY_URL or not GROQ_API_KEY:
        raise ValueError("CF_AI_GATEWAY_URL or GROQ_API_KEY not set")

    # Cloudflare AI Gateway Groq endpoint
    endpoint = f"{CF_AI_GATEWAY_URL}/groq/openai/v1/chat/completions"

    payload = json.dumps({
        "model": GROQ_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 700,
        "temperature": 0.7,
    }).encode()

    req = Request(
        endpoint,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type":  "application/json",
        },
    )
    with urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode())

    return data["choices"][0]["message"]["content"].strip()

def call_gemini_fallback(prompt):
    """
    Fallback: call Gemini 2.0 Flash Lite through Cloudflare AI Gateway.
    Gateway URL format: .../google-ai-studio
    Requires GEMINI_API_KEY in environment.
    """
    gemini_key = os.environ.get("GEMINI_API_KEY", "")
    if not gemini_key or not CF_AI_GATEWAY_URL:
        raise ValueError("GEMINI_API_KEY or CF_AI_GATEWAY_URL not set")

    endpoint = (
        f"{CF_AI_GATEWAY_URL}/google-ai-studio/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent"
    )

    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": 700, "temperature": 0.7},
    }).encode()

    req = Request(
        endpoint,
        data=payload,
        method="POST",
        headers={
            "x-goog-api-key": gemini_key,
            "Content-Type":   "application/json",
        },
    )
    with urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode())

    return data["candidates"][0]["content"]["parts"][0]["text"].strip()

def parse_retry_delay(error_str):
    m = re.search(r"retry in (\d+(?:\.\d+)?)", str(error_str), re.IGNORECASE)
    if m:
        return int(float(m.group(1))) + 2
    m2 = re.search(r"\"retryDelay\":\s*\"(\d+)", str(error_str))
    if m2:
        return int(m2.group(1)) + 2
    return 30

def generate_analysis(title, snippet, article_text, category):
    """
    Try Groq via AI Gateway → Gemini fallback → structured snippet.
    Returns (text, has_ai: bool)
    """
    prompt = build_prompt(title, snippet, article_text, category)

    # ── Primary: Groq via Cloudflare AI Gateway ──────────────────────────
    for attempt in range(MAX_RETRIES):
        try:
            text = call_groq_via_gateway(prompt)
            if text:
                print(f"  ✓ Groq LLaMA 3.3 70B via AI Gateway: {len(text)} chars")
                return text, True
        except Exception as e:
            err = str(e)
            if "429" in err or "rate" in err.lower() or "quota" in err.lower():
                wait = parse_retry_delay(err)
                print(f"  Groq rate limited (attempt {attempt+1}/{MAX_RETRIES}). Waiting {wait}s…")
                time.sleep(wait)
            else:
                print(f"  Groq error: {err[:120]}")
                break

    # ── Fallback: Gemini via Cloudflare AI Gateway ───────────────────────
    print("  Trying Gemini fallback via AI Gateway…")
    for attempt in range(MAX_RETRIES):
        try:
            text = call_gemini_fallback(prompt)
            if text:
                print(f"  ✓ Gemini fallback via AI Gateway: {len(text)} chars")
                return text, True
        except Exception as e:
            err = str(e)
            if "429" in err or "quota" in err.lower():
                wait = parse_retry_delay(err)
                print(f"  Gemini rate limited (attempt {attempt+1}/{MAX_RETRIES}). Waiting {wait}s…")
                time.sleep(wait)
            else:
                print(f"  Gemini error: {err[:120]}")
                break

    # ── Final fallback: structured snippet ───────────────────────────────
    print("  All AI models failed — using structured fallback")
    cat_label = CATEGORY_META.get(category, {}).get("label", category)
    fallback = (
        f"The {cat_label} space has seen a significant development: {title}. "
        f"{snippet} "
        f"As practitioners in this field, it is essential to recognise the regulatory "
        f"implications of such developments. Legal teams advising clients in the "
        f"{cat_label} sector must closely monitor evolving frameworks to ensure continued "
        f"compliance. Founders and investors should seek immediate legal counsel to "
        f"understand how this development may affect their operations, licensing "
        f"obligations, and risk exposure. Web3Legals specialises in exactly this kind "
        f"of cross-jurisdictional legal analysis. Reach out via the contact page for "
        f"a free consultation tailored to your specific situation."
    )
    return fallback, False

# ── HTML Generation ───────────────────────────────────────────────────────────

def article_html(title, analysis, category, source_url, pub_display):
    cat        = CATEGORY_META.get(category, CATEGORY_META["crypto"])
    paragraphs = "\n".join(
        f"      <p>{p.strip()}</p>"
        for p in analysis.split("\n")
        if p.strip()
    )
    safe_title = title.replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")
    year       = datetime.now().year

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{safe_title} | Web3Legals</title>
  <meta name="description" content="{safe_title[:155]}" />
  <link rel="stylesheet" href="/css/style.css" />
  <style>
    body {{ background:#0a0b0f; color:#d4d8e2; font-family:'Inter',sans-serif; margin:0; }}

    /* ── Hero ── */
    .art-hero {{
      background: linear-gradient(135deg,#0d1117 0%,#0f1923 55%,#0a0b0f 100%);
      border-bottom: 1px solid #1e2535;
      padding: 88px 24px 52px;
      text-align: center;
    }}
    .art-hero .back {{
      display:inline-flex; align-items:center; gap:6px;
      color:#00d4ff; text-decoration:none; font-size:.82rem;
      font-weight:600; letter-spacing:.06em; text-transform:uppercase;
      margin-bottom:28px; transition:opacity .2s;
    }}
    .art-hero .back:hover {{ opacity:.65; }}
    .art-hero .badge {{
      display:inline-block; padding:4px 13px; border-radius:4px;
      background:#00d4ff1a; color:#00d4ff; font-size:.7rem;
      font-weight:700; letter-spacing:.12em; text-transform:uppercase;
      border:1px solid #00d4ff40; margin-bottom:22px;
    }}
    .art-hero h1 {{
      font-size:clamp(1.45rem,4vw,2.35rem); font-weight:700;
      color:#f0f4ff; line-height:1.3; max-width:820px;
      margin:0 auto 18px; letter-spacing:-.015em;
    }}
    .art-hero .meta {{ font-size:.82rem; color:#6b7a99; }}
    .art-hero .meta span {{ margin:0 6px; }}

    /* ── Body ── */
    .art-body {{
      max-width:760px; margin:0 auto; padding:52px 24px 72px;
    }}
    .art-body p {{
      font-size:1.05rem; line-height:1.9; color:#b8c0d4; margin:0 0 22px;
    }}
    .art-body p:first-child::first-letter {{
      font-size:3.4em; font-weight:800; color:#00d4ff;
      float:left; line-height:.72; margin:8px 12px 0 0;
      font-family:'Georgia',serif;
    }}

    /* ── Source bar ── */
    .art-source {{
      max-width:760px; margin:0 auto 40px;
      padding:20px 24px 0; border-top:1px solid #1e2535;
      display:flex; align-items:flex-start; gap:10px; flex-wrap:wrap;
    }}
    .art-source .lbl {{ font-size:.78rem; color:#6b7a99; white-space:nowrap; padding-top:2px; }}
    .art-source a {{
      color:#00d4ff; font-size:.78rem; text-decoration:none;
      word-break:break-all;
    }}
    .art-source a:hover {{ text-decoration:underline; }}

    /* ── CTA ── */
    .art-cta {{
      background:linear-gradient(135deg,#00d4ff0d,#0066ff0d);
      border:1px solid #00d4ff30; border-radius:12px;
      max-width:760px; margin:0 auto 80px; padding:38px 32px;
      text-align:center;
    }}
    .art-cta h3 {{ color:#f0f4ff; font-size:1.2rem; margin:0 0 8px; font-weight:600; }}
    .art-cta p  {{ color:#6b7a99; font-size:.88rem; margin:0 0 22px; }}
    .art-cta a  {{
      display:inline-block; padding:13px 30px; border-radius:6px;
      background:linear-gradient(135deg,#00d4ff,#0066ff);
      color:#fff; font-weight:600; text-decoration:none; font-size:.9rem;
      transition:opacity .2s;
    }}
    .art-cta a:hover {{ opacity:.82; }}
  </style>
</head>
<body>

  <nav class="navbar">
    <div class="nav-container">
      <a href="/index.html" class="logo">Web3<span>Legals</span></a>
      <ul class="nav-links">
        <li><a href="/index.html">Home</a></li>
        <li><a href="/about.html">About</a></li>
        <li><a href="/services.html">Services</a></li>
        <li><a href="/blog/">Blog</a></li>
        <li><a href="/contact.html">Contact</a></li>
      </ul>
      <a href="/contact.html" class="cta-btn">Free Consultation</a>
      <button class="mobile-menu-btn" aria-label="Toggle menu">&#9776;</button>
    </div>
  </nav>

  <div class="art-hero">
    <a href="/blog/" class="back">← Back to Blog</a>
    <div class="badge">{cat['emoji']} {cat['badge']}</div>
    <h1>{safe_title}</h1>
    <p class="meta">
      <span>By Rahul Pareek</span>·
      <span>{pub_display}</span>·
      <span>{cat['label']}</span>
    </p>
  </div>

  <div class="art-body">
{paragraphs}
  </div>

  <div class="art-source">
    <span class="lbl">Original source:</span>
    <a href="{source_url}" target="_blank" rel="noopener noreferrer">
      {source_url[:100]}{"…" if len(source_url) > 100 else ""}
    </a>
  </div>

  <div class="art-cta">
    <h3>Need Legal Clarity on This?</h3>
    <p>Get tailored advice from India's leading Web3 &amp; fintech legal expert.</p>
    <a href="/contact.html">Book a Free Consultation</a>
  </div>

  <footer class="footer">
    <div class="footer-container">
      <div class="footer-brand">
        <a href="/index.html" class="logo">Web3<span>Legals</span></a>
        <p>India's leading legal firm for Web3, crypto, and fintech businesses.</p>
      </div>
      <div class="footer-links">
        <h4>Quick Links</h4>
        <ul>
          <li><a href="/index.html">Home</a></li>
          <li><a href="/about.html">About</a></li>
          <li><a href="/services.html">Services</a></li>
          <li><a href="/blog/">Blog</a></li>
          <li><a href="/contact.html">Contact</a></li>
        </ul>
      </div>
      <div class="footer-contact">
        <h4>Contact</h4>
        <p>Email: rahul@web3legals.com</p>
        <p>Web3Legals | New Delhi, India</p>
      </div>
    </div>
    <div class="footer-bottom">
      <p>&copy; {year} Web3Legals. All rights reserved.</p>
    </div>
  </footer>

  <script src="/js/main.js"></script>
</body>
</html>
"""

def blog_index_html(all_articles):
    year  = datetime.now().year
    total = len(all_articles)

    cards = []
    for art in all_articles:
        cat     = art.get("category", "crypto")
        meta    = CATEGORY_META.get(cat, CATEGORY_META["crypto"])
        slug    = art.get("slug", "")
        title   = art.get("title", "")
        snippet = (art.get("snippet") or "")[:160]
        pub     = art.get("pub_display", "")
        has_ai  = bool(art.get("has_ai") or art.get("has_ai") == 1)
        ai_tag  = "✦ AI Analysis" if has_ai else "📰 News Brief"

        cards.append(f"""        <div class="card" data-cat="{cat}">
          <div class="card-badge">{meta['emoji']} {meta['badge']}</div>
          <h3 class="card-title">{title}</h3>
          <p class="card-snippet">{snippet}{"…" if len(snippet)==160 else ""}</p>
          <div class="card-footer">
            <span class="card-meta">{pub} · <em>{ai_tag}</em></span>
            <a class="card-read" href="/blog/{slug}.html">Read →</a>
          </div>
        </div>""")

    cards_html = "\n".join(cards) if cards else \
        '        <p class="empty">No articles yet — check back soon.</p>'

    filter_btns = [
        ("all",         "All Articles"),
        ("crypto",      "Crypto Law"),
        ("fintech",     "Fintech"),
        ("india-legal", "India Courts"),
        ("dao",         "DAO & Governance"),
        ("compliance",  "Compliance"),
        ("token",       "Token Law"),
    ]
    btns_html = "\n".join(
        f'      <button class="fbtn{" active" if k=="all" else ""}" '
        f'data-filter="{k}">{label}</button>'
        for k, label in filter_btns
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Legal Intelligence Blog | Web3Legals</title>
  <meta name="description" content="Expert legal analysis on crypto regulation, fintech law, and Indian courts — by Rahul Pareek, Web3Legals." />
  <link rel="stylesheet" href="/css/style.css" />
  <style>
    body {{ background:#0a0b0f; color:#d4d8e2; font-family:'Inter',sans-serif; margin:0; }}

    .blog-hero {{
      background:linear-gradient(135deg,#0d1117 0%,#0f1923 60%,#0a0b0f 100%);
      border-bottom:1px solid #1e2535;
      padding:100px 24px 60px; text-align:center;
    }}
    .blog-hero .eyebrow {{
      font-size:.74rem; font-weight:700; letter-spacing:.16em;
      text-transform:uppercase; color:#00d4ff; margin-bottom:14px;
    }}
    .blog-hero h1 {{
      font-size:clamp(1.9rem,5vw,3.1rem); font-weight:800;
      color:#f0f4ff; margin:0 0 14px; letter-spacing:-.022em; line-height:1.15;
    }}
    .blog-hero h1 span {{ color:#00d4ff; }}
    .blog-hero .sub {{
      font-size:1rem; color:#6b7a99; max-width:540px;
      margin:0 auto; line-height:1.7;
    }}
    .blog-hero .pill {{
      display:inline-block; margin-top:20px; padding:6px 18px;
      border-radius:20px; background:#00d4ff12; border:1px solid #00d4ff30;
      color:#00d4ff; font-size:.78rem; font-weight:600;
    }}

    .filters {{
      display:flex; flex-wrap:wrap; gap:10px;
      justify-content:center; padding:36px 24px 0;
    }}
    .fbtn {{
      padding:8px 18px; border-radius:6px; border:1px solid #2a3245;
      background:transparent; color:#8a94b0; cursor:pointer;
      font-size:.82rem; font-weight:500; transition:all .2s;
    }}
    .fbtn:hover,.fbtn.active {{
      background:#00d4ff12; border-color:#00d4ff50; color:#00d4ff;
    }}

    .grid {{
      max-width:1200px; margin:40px auto 80px; padding:0 24px;
      display:grid; grid-template-columns:repeat(auto-fill,minmax(310px,1fr));
      gap:24px;
    }}
    .card {{
      background:#0f1420; border:1px solid #1e2535; border-radius:10px;
      padding:26px; display:flex; flex-direction:column;
      transition:border-color .2s,transform .2s;
    }}
    .card:hover {{ border-color:#00d4ff40; transform:translateY(-3px); }}
    .card.hidden {{ display:none; }}
    .card-badge {{
      font-size:.7rem; font-weight:700; letter-spacing:.11em;
      text-transform:uppercase; color:#00d4ff;
      background:#00d4ff10; border:1px solid #00d4ff30;
      border-radius:4px; padding:3px 9px;
      display:inline-block; width:fit-content; margin-bottom:14px;
    }}
    .card-title {{
      font-size:.97rem; font-weight:600; color:#e8edf8;
      line-height:1.45; margin:0 0 12px; flex-grow:1;
    }}
    .card-snippet {{
      font-size:.85rem; color:#6b7a99; line-height:1.65; margin:0 0 18px;
    }}
    .card-footer {{
      display:flex; justify-content:space-between; align-items:center;
      border-top:1px solid #1e2535; padding-top:14px; margin-top:auto;
    }}
    .card-meta {{ font-size:.74rem; color:#4a5568; }}
    .card-meta em {{ font-style:normal; color:#2e7d5e; }}
    .card-read {{
      font-size:.82rem; font-weight:600; color:#00d4ff;
      text-decoration:none; transition:opacity .2s;
    }}
    .card-read:hover {{ opacity:.65; }}
    .empty {{
      text-align:center; color:#4a5568;
      padding:64px 0; grid-column:1/-1;
    }}

    @media(max-width:600px) {{
      .grid {{ grid-template-columns:1fr; }}
      .filters {{ gap:8px; }}
      .fbtn {{ font-size:.78rem; padding:7px 14px; }}
    }}
  </style>
</head>
<body>

  <nav class="navbar">
    <div class="nav-container">
      <a href="/index.html" class="logo">Web3<span>Legals</span></a>
      <ul class="nav-links">
        <li><a href="/index.html">Home</a></li>
        <li><a href="/about.html">About</a></li>
        <li><a href="/services.html">Services</a></li>
        <li><a href="/blog/" class="active">Blog</a></li>
        <li><a href="/contact.html">Contact</a></li>
      </ul>
      <a href="/contact.html" class="cta-btn">Free Consultation</a>
      <button class="mobile-menu-btn" aria-label="Toggle menu">&#9776;</button>
    </div>
  </nav>

  <div class="blog-hero">
    <div class="eyebrow">Legal Intelligence</div>
    <h1>Crypto &amp; Fintech <span>Law Blog</span></h1>
    <p class="sub">Original analysis on crypto regulation, fintech law, and Indian courts —
      by Rahul Pareek, Double Gold Medallist LLM, NLU India.</p>
    <div class="pill">{total} article{"s" if total != 1 else ""} published</div>
  </div>

  <div class="filters">
{btns_html}
  </div>

  <div class="grid" id="grid">
{cards_html}
  </div>

  <footer class="footer">
    <div class="footer-container">
      <div class="footer-brand">
        <a href="/index.html" class="logo">Web3<span>Legals</span></a>
        <p>India's leading legal firm for Web3, crypto, and fintech businesses.</p>
      </div>
      <div class="footer-links">
        <h4>Quick Links</h4>
        <ul>
          <li><a href="/index.html">Home</a></li>
          <li><a href="/about.html">About</a></li>
          <li><a href="/services.html">Services</a></li>
          <li><a href="/blog/">Blog</a></li>
          <li><a href="/contact.html">Contact</a></li>
        </ul>
      </div>
      <div class="footer-contact">
        <h4>Contact</h4>
        <p>Email: rahul@web3legals.com</p>
        <p>Web3Legals | New Delhi, India</p>
      </div>
    </div>
    <div class="footer-bottom">
      <p>&copy; {year} Web3Legals. All rights reserved.</p>
    </div>
  </footer>

  <script>
    /* Pure static filter — no fetch, no external calls */
    (function() {{
      var btns  = document.querySelectorAll('.fbtn');
      var cards = document.querySelectorAll('.card');
      btns.forEach(function(btn) {{
        btn.addEventListener('click', function() {{
          btns.forEach(function(b) {{ b.classList.remove('active'); }});
          btn.classList.add('active');
          var f = btn.getAttribute('data-filter');
          cards.forEach(function(card) {{
            card.classList.toggle('hidden',
              f !== 'all' && card.getAttribute('data-cat') !== f);
          }});
        }});
      }});
    }})();
  </script>
  <script src="/js/main.js"></script>
</body>
</html>
"""

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  Web3Legals Crypto Radar — Phase 1 Hybrid Architecture")
    print("=" * 60)
    print(f"  Run time : {datetime.now(timezone.utc).isoformat()}")
    print(f"  AI route : Groq via Cloudflare AI Gateway → Gemini fallback")
    print(f"  DB       : Cloudflare D1 via Worker bridge")
    print(f"  Max      : {MAX_ARTICLES} articles/run")
    print("=" * 60)

    # ── Step 1: Fetch all RSS feeds ──────────────────────────────────────
    print("\n[1/5] Fetching RSS feeds…")
    candidates = []
    for category, feed_url in RSS_FEEDS:
        print(f"  {category}: {feed_url[40:80]}…")
        items = fetch_rss(feed_url, category)
        for item in items:
            item["aid"] = article_id(item["url"])
            candidates.append(item)
    print(f"  Total raw items: {len(candidates)}")

    # Deduplicate within this batch
    seen_this_batch = set()
    unique = []
    for c in candidates:
        if c["aid"] not in seen_this_batch:
            seen_this_batch.add(c["aid"])
            unique.append(c)
    print(f"  Unique this batch: {len(unique)}")

    # ── Step 2: Check D1 for already-seen articles ───────────────────────
    print("\n[2/5] Checking Cloudflare D1 for seen articles…")
    all_aids  = [c["aid"] for c in unique]
    seen_aids = d1_check_seen(all_aids)
    print(f"  Already seen: {len(seen_aids)}")

    new_items = [c for c in unique if c["aid"] not in seen_aids]
    print(f"  New articles : {len(new_items)}")

    to_process = new_items[:MAX_ARTICLES]
    print(f"  Processing   : {len(to_process)}")

    if not to_process:
        print("\nNo new articles today. Exiting.")
        return

    # ── Step 3: Generate articles ─────────────────────────────────────────
    print("\n[3/5] Generating articles…")
    os.makedirs(BLOG_DIR, exist_ok=True)
    new_metadata = []

    for i, art in enumerate(to_process):
        print(f"\n  [{i+1}/{len(to_process)}] {art['title'][:65]}…")

        # Try to get full article text
        art_text = fetch_article_text(art["url"])
        if art_text:
            print(f"    Full text: {len(art_text)} chars")
        else:
            print("    Using RSS snippet as context")

        # Generate via AI Gateway
        analysis, has_ai = generate_analysis(
            art["title"], art["snippet"], art_text, art["category"]
        )

        slug        = slugify(art["title"])
        pub_display = format_display_date(art.get("pubdate", ""))

        # Save HTML file
        html     = article_html(art["title"], analysis, art["category"],
                                art["url"], pub_display)
        out_path = os.path.join(BLOG_DIR, f"{slug}.html")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"    Saved: {out_path} ({'AI' if has_ai else 'fallback'})")

        new_metadata.append({
            "aid":         art["aid"],
            "title":       art["title"],
            "slug":        slug,
            "category":    art["category"],
            "snippet":     art["snippet"],
            "url":         art["url"],
            "pub_display": pub_display,
            "has_ai":      has_ai,
            "generated":   datetime.now(timezone.utc).isoformat(),
        })

        if i < len(to_process) - 1:
            print(f"    Waiting {DELAY_SECONDS}s…")
            time.sleep(DELAY_SECONDS)

    # ── Step 4: Update D1 ─────────────────────────────────────────────────
    print("\n[4/5] Updating Cloudflare D1…")
    d1_mark_seen([m["aid"] for m in new_metadata])
    d1_upsert_articles(new_metadata)

    # Also keep a local backup in .all_articles.json for safety
    all_arts = d1_get_all_articles()
    with open(".all_articles.json", "w", encoding="utf-8") as f:
        json.dump(all_arts, f, indent=2, ensure_ascii=False)
    print(f"  Local backup: .all_articles.json ({len(all_arts)} articles)")

    # ── Step 5: Rebuild blog/index.html ──────────────────────────────────
    print("\n[5/5] Rebuilding blog/index.html…")
    index_html = blog_index_html(all_arts)
    index_path = os.path.join(BLOG_DIR, "index.html")
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(index_html)
    print(f"  Rebuilt: {index_path} ({len(all_arts)} total articles)")

    print("\n" + "=" * 60)
    print(f"  Done! {len(new_metadata)} new articles published.")
    print(f"  Total in blog: {len(all_arts)}")
    print("  git commit + push will trigger Cloudflare Pages deploy.")
    print("=" * 60)

if __name__ == "__main__":
    main()
