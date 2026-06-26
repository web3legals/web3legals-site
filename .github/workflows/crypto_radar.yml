#!/usr/bin/env python3
"""
crypto_radar.py — Web3Legals Auto-Publishing Blog System
Phase 1 v4: OpenRouter (free, no bot-block) → Gemini direct fallback
"""

import os, json, time, hashlib, re, textwrap
from datetime import datetime, timezone
from urllib.request import urlopen, Request
from urllib.error import HTTPError
import xml.etree.ElementTree as ET

# ── Secrets ───────────────────────────────────────────────────────────────────
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
GEMINI_API_KEY     = os.environ.get("GEMINI_API_KEY", "")
CF_WORKER_URL      = os.environ.get("CF_WORKER_URL", "").rstrip("/")
CF_WORKER_SECRET   = os.environ.get("CF_WORKER_SECRET", "")

# ── Config ────────────────────────────────────────────────────────────────────
MAX_ARTICLES  = 5
DELAY_SECONDS = 5
MAX_RETRIES   = 3
BLOG_DIR      = "blog"

# OpenRouter free models (fallback chain)
OR_MODELS = [
    "meta-llama/llama-3.3-70b-instruct:free",
    "mistralai/mistral-7b-instruct:free",
    "google/gemma-3-27b-it:free",
]
GEMINI_MODEL = "gemini-2.0-flash-lite"

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

# ── Helpers ───────────────────────────────────────────────────────────────────
def article_id(url):
    return hashlib.md5(url.encode()).hexdigest()[:12]

def slugify(title):
    slug = re.sub(r"[^\w\s-]", "", title.lower())
    slug = re.sub(r"[\s_]+", "-", slug).strip("-")
    return slug[:80]

def format_display_date(s):
    for fmt in ["%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S GMT", "%a, %d %b %Y %H:%M:%S +0000"]:
        try:
            return datetime.strptime(s.strip(), fmt).strftime("%B %d, %Y")
        except Exception:
            continue
    return datetime.now(timezone.utc).strftime("%B %d, %Y")

def http_post(url, payload, headers):
    data = json.dumps(payload).encode()
    req  = Request(url, data=data, method="POST", headers=headers)
    with urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())

def http_get_json(url, headers):
    req = Request(url, method="GET", headers=headers)
    with urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())

def parse_retry(err):
    m = re.search(r"retry in (\d+(?:\.\d+)?)", str(err), re.I)
    return int(float(m.group(1))) + 2 if m else 30

# ── D1 Bridge ─────────────────────────────────────────────────────────────────
def worker_call(method, path, body=None):
    if not CF_WORKER_URL or not CF_WORKER_SECRET:
        return None
    url = f"{CF_WORKER_URL}{path}"
    hdrs = {"Authorization": f"Bearer {CF_WORKER_SECRET}", "Content-Type": "application/json"}
    try:
        return http_post(url, body, hdrs) if method == "POST" else http_get_json(url, hdrs)
    except Exception as e:
        print(f"  Worker [{method} {path}]: {str(e)[:80]}")
        return None

def d1_check_seen(aids):
    r = worker_call("POST", "/seen/check", {"aids": aids})
    if r and "seen" in r:
        return set(r["seen"])
    if os.path.exists(".seen_articles.json"):
        return set(json.load(open(".seen_articles.json")))
    return set()

def d1_mark_seen(aids):
    if not worker_call("POST", "/seen/add", {"aids": aids}):
        seen = set(json.load(open(".seen_articles.json"))) if os.path.exists(".seen_articles.json") else set()
        seen.update(aids)
        json.dump(list(seen), open(".seen_articles.json", "w"))

def d1_upsert(articles):
    worker_call("POST", "/articles/upsert", {"articles": articles})

def d1_get_all():
    r = worker_call("GET", "/articles?limit=500")
    if r and "articles" in r:
        return r["articles"]
    if os.path.exists(".all_articles.json"):
        return json.load(open(".all_articles.json"))
    return []

# ── RSS ───────────────────────────────────────────────────────────────────────
def fetch_rss(url, category):
    items = []
    try:
        req = Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; Web3Legals/1.0)"})
        with urlopen(req, timeout=15) as resp:
            root = ET.fromstring(resp.read())
        ch = root.find("channel")
        if ch is None: return items
        for item in ch.findall("item"):
            t = item.find("title"); l = item.find("link")
            d = item.find("description"); p = item.find("pubDate")
            if t is None or l is None: continue
            title = (t.text or "").strip()
            if len(title) < 10: continue
            snippet = re.sub(r"<[^>]+>", "", (d.text or "") if d is not None else "").strip()
            items.append({
                "title": title, "url": (l.text or "").strip(),
                "snippet": snippet[:400],
                "pubdate": (p.text or "").strip() if p is not None else "",
                "category": category,
            })
    except Exception as e:
        print(f"  RSS error: {e}")
    return items

def fetch_article_text(url):
    try:
        from newspaper import Article
        a = Article(url); a.download(); a.parse()
        return (a.text or "").strip()[:3000]
    except Exception:
        return ""

# ── AI Generation ─────────────────────────────────────────────────────────────
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
        Context: {context}

        Requirements:
        - Write in first person as Rahul Pareek
        - Open with a sharp, specific legal observation — not a generic intro
        - Cite relevant laws (SEC, CFTC, MiCA, RBI, SEBI, IPC, IT Act, PMLA, FEMA)
        - Explain practical implications for founders, investors, compliance teams
        - End with a concrete takeaway or recommended action
        - Exactly 400 words, plain paragraphs only, no markdown, no bullets
        - Do NOT repeat the news title verbatim in the first sentence
    """).strip()

def call_openrouter(prompt, model):
    """Call OpenRouter — no Cloudflare bot protection, works from GitHub Actions."""
    if not OPENROUTER_API_KEY:
        raise ValueError("OPENROUTER_API_KEY not set")
    result = http_post(
        "https://openrouter.ai/api/v1/chat/completions",
        {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 700,
            "temperature": 0.7,
        },
        {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://web3legals.com",
            "X-Title": "Web3Legals Blog",
        }
    )
    return result["choices"][0]["message"]["content"].strip()

def call_gemini_direct(prompt):
    """Call Gemini directly — not Cloudflare protected."""
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY not set")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    result = http_post(
        url,
        {"contents": [{"parts": [{"text": prompt}]}],
         "generationConfig": {"maxOutputTokens": 700, "temperature": 0.7}},
        {"Content-Type": "application/json"}
    )
    return result["candidates"][0]["content"]["parts"][0]["text"].strip()

def generate_analysis(title, snippet, article_text, category):
    prompt = build_prompt(title, snippet, article_text, category)

    # ── Try each OpenRouter free model ───────────────────────────────────
    for model in OR_MODELS:
        for attempt in range(MAX_RETRIES):
            try:
                text = call_openrouter(prompt, model)
                if text:
                    print(f"  ✓ OpenRouter [{model.split('/')[1]}]: {len(text)} chars")
                    return text, True
            except HTTPError as e:
                body = ""
                try: body = e.read().decode()
                except: pass
                if e.code == 429:
                    wait = parse_retry(body)
                    print(f"  OpenRouter rate limited (attempt {attempt+1}). Waiting {wait}s…")
                    time.sleep(wait)
                elif e.code in (402, 403):
                    print(f"  OpenRouter {e.code} on {model} — trying next model")
                    break
                else:
                    print(f"  OpenRouter HTTP {e.code}: {body[:150]}")
                    break
            except Exception as e:
                print(f"  OpenRouter error [{model}]: {str(e)[:150]}")
                break

    # ── Gemini direct fallback ───────────────────────────────────────────
    print("  Trying Gemini direct…")
    for attempt in range(MAX_RETRIES):
        try:
            text = call_gemini_direct(prompt)
            if text:
                print(f"  ✓ Gemini direct: {len(text)} chars")
                return text, True
        except HTTPError as e:
            body = ""
            try: body = e.read().decode()
            except: pass
            if e.code == 429:
                wait = parse_retry(body)
                print(f"  Gemini rate limited (attempt {attempt+1}). Waiting {wait}s…")
                time.sleep(wait)
            else:
                print(f"  Gemini HTTP {e.code}: {body[:150]}")
                break
        except Exception as e:
            print(f"  Gemini error: {str(e)[:150]}")
            break

    # ── Structured fallback ──────────────────────────────────────────────
    print("  All AI failed — structured fallback")
    cat_label = CATEGORY_META.get(category, {}).get("label", category)
    return (
        f"The {cat_label} space continues to evolve rapidly, and this latest development demands attention: {title}. "
        f"{snippet} "
        f"From a legal standpoint, practitioners advising clients in the {cat_label} sector must closely monitor "
        f"such regulatory shifts to ensure continued compliance with applicable frameworks including PMLA, FEMA, "
        f"RBI guidelines, and international standards such as FATF recommendations. "
        f"Founders and investors should seek immediate legal counsel to understand how this development "
        f"may affect their operations, licensing obligations, and risk exposure. "
        f"Web3Legals specialises in cross-jurisdictional legal analysis for exactly these scenarios. "
        f"Reach out via our contact page for a free consultation tailored to your specific situation."
    ), False

# ── HTML ──────────────────────────────────────────────────────────────────────
def article_html(title, analysis, category, source_url, pub_display):
    cat  = CATEGORY_META.get(category, CATEGORY_META["crypto"])
    paras = "\n".join(f"      <p>{p.strip()}</p>" for p in analysis.split("\n") if p.strip())
    safe  = title.replace('"',"&quot;").replace("<","&lt;").replace(">","&gt;")
    year  = datetime.now().year
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>{safe} | Web3Legals</title>
  <meta name="description" content="{safe[:155]}"/>
  <link rel="stylesheet" href="/css/style.css"/>
  <style>
    body{{background:#0a0b0f;color:#d4d8e2;font-family:'Inter',sans-serif;margin:0}}
    .art-hero{{background:linear-gradient(135deg,#0d1117 0%,#0f1923 55%,#0a0b0f 100%);border-bottom:1px solid #1e2535;padding:88px 24px 52px;text-align:center}}
    .art-hero .back{{display:inline-flex;align-items:center;gap:6px;color:#00d4ff;text-decoration:none;font-size:.82rem;font-weight:600;letter-spacing:.06em;text-transform:uppercase;margin-bottom:28px;transition:opacity .2s}}
    .art-hero .back:hover{{opacity:.65}}
    .art-hero .badge{{display:inline-block;padding:4px 13px;border-radius:4px;background:#00d4ff1a;color:#00d4ff;font-size:.7rem;font-weight:700;letter-spacing:.12em;text-transform:uppercase;border:1px solid #00d4ff40;margin-bottom:22px}}
    .art-hero h1{{font-size:clamp(1.45rem,4vw,2.35rem);font-weight:700;color:#f0f4ff;line-height:1.3;max-width:820px;margin:0 auto 18px}}
    .art-hero .meta{{font-size:.82rem;color:#6b7a99}}
    .art-hero .meta span{{margin:0 6px}}
    .art-body{{max-width:760px;margin:0 auto;padding:52px 24px 72px}}
    .art-body p{{font-size:1.05rem;line-height:1.9;color:#b8c0d4;margin:0 0 22px}}
    .art-body p:first-child::first-letter{{font-size:3.4em;font-weight:800;color:#00d4ff;float:left;line-height:.72;margin:8px 12px 0 0;font-family:'Georgia',serif}}
    .art-source{{max-width:760px;margin:0 auto 40px;padding:20px 24px 0;border-top:1px solid #1e2535;display:flex;align-items:flex-start;gap:10px;flex-wrap:wrap}}
    .art-source .lbl{{font-size:.78rem;color:#6b7a99;white-space:nowrap}}
    .art-source a{{color:#00d4ff;font-size:.78rem;text-decoration:none;word-break:break-all}}
    .art-cta{{background:linear-gradient(135deg,#00d4ff0d,#0066ff0d);border:1px solid #00d4ff30;border-radius:12px;max-width:760px;margin:0 auto 80px;padding:38px 32px;text-align:center}}
    .art-cta h3{{color:#f0f4ff;font-size:1.2rem;margin:0 0 8px;font-weight:600}}
    .art-cta p{{color:#6b7a99;font-size:.88rem;margin:0 0 22px}}
    .art-cta a{{display:inline-block;padding:13px 30px;border-radius:6px;background:linear-gradient(135deg,#00d4ff,#0066ff);color:#fff;font-weight:600;text-decoration:none;font-size:.9rem;transition:opacity .2s}}
    .art-cta a:hover{{opacity:.82}}
  </style>
</head>
<body>
  <nav class="navbar"><div class="nav-container">
    <a href="/index.html" class="logo">Web3<span>Legals</span></a>
    <ul class="nav-links">
      <li><a href="/index.html">Home</a></li><li><a href="/about.html">About</a></li>
      <li><a href="/services.html">Services</a></li><li><a href="/blog/">Blog</a></li>
      <li><a href="/contact.html">Contact</a></li>
    </ul>
    <a href="/contact.html" class="cta-btn">Free Consultation</a>
    <button class="mobile-menu-btn" aria-label="Toggle menu">&#9776;</button>
  </div></nav>
  <div class="art-hero">
    <a href="/blog/" class="back">← Back to Blog</a>
    <div class="badge">{cat['emoji']} {cat['badge']}</div>
    <h1>{safe}</h1>
    <p class="meta"><span>By Rahul Pareek</span>·<span>{pub_display}</span>·<span>{cat['label']}</span></p>
  </div>
  <div class="art-body">
{paras}
  </div>
  <div class="art-source">
    <span class="lbl">Original source:</span>
    <a href="{source_url}" target="_blank" rel="noopener noreferrer">{source_url[:100]}{"…" if len(source_url)>100 else ""}</a>
  </div>
  <div class="art-cta">
    <h3>Need Legal Clarity on This?</h3>
    <p>Get tailored advice from India's leading Web3 &amp; fintech legal expert.</p>
    <a href="/contact.html">Book a Free Consultation</a>
  </div>
  <footer class="footer"><div class="footer-container">
    <div class="footer-brand">
      <a href="/index.html" class="logo">Web3<span>Legals</span></a>
      <p>India's leading legal firm for Web3, crypto, and fintech businesses.</p>
    </div>
    <div class="footer-links"><h4>Quick Links</h4>
      <ul><li><a href="/index.html">Home</a></li><li><a href="/about.html">About</a></li>
      <li><a href="/services.html">Services</a></li><li><a href="/blog/">Blog</a></li>
      <li><a href="/contact.html">Contact</a></li></ul>
    </div>
    <div class="footer-contact"><h4>Contact</h4>
      <p>Email: rahul@web3legals.com</p><p>Web3Legals | New Delhi, India</p>
    </div>
  </div>
  <div class="footer-bottom"><p>&copy; {year} Web3Legals. All rights reserved.</p></div>
  </footer>
  <script src="/js/main.js"></script>
</body></html>
"""

def blog_index_html(all_articles):
    year  = datetime.now().year
    total = len(all_articles)
    cards = []
    for art in all_articles:
        cat    = art.get("category","crypto")
        meta   = CATEGORY_META.get(cat, CATEGORY_META["crypto"])
        slug   = art.get("slug","")
        title  = art.get("title","")
        snip   = (art.get("snippet") or "")[:160]
        pub    = art.get("pub_display","")
        ai_tag = "✦ AI Analysis" if art.get("has_ai") else "📰 News Brief"
        cards.append(f"""        <div class="card" data-cat="{cat}">
          <div class="card-badge">{meta['emoji']} {meta['badge']}</div>
          <h3 class="card-title">{title}</h3>
          <p class="card-snippet">{snip}{"…" if len(snip)==160 else ""}</p>
          <div class="card-footer">
            <span class="card-meta">{pub} · <em>{ai_tag}</em></span>
            <a class="card-read" href="/blog/{slug}.html">Read →</a>
          </div>
        </div>""")
    cards_html = "\n".join(cards) if cards else '<p class="empty">No articles yet.</p>'
    btns = [("all","All Articles"),("crypto","Crypto Law"),("fintech","Fintech"),
            ("india-legal","India Courts"),("dao","DAO & Governance"),
            ("compliance","Compliance"),("token","Token Law")]
    btns_html = "\n".join(
        f'      <button class="fbtn{" active" if k=="all" else ""}" data-filter="{k}">{v}</button>'
        for k,v in btns)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>Legal Intelligence Blog | Web3Legals</title>
  <meta name="description" content="Expert legal analysis on crypto regulation, fintech law, and Indian courts."/>
  <link rel="stylesheet" href="/css/style.css"/>
  <style>
    body{{background:#0a0b0f;color:#d4d8e2;font-family:'Inter',sans-serif;margin:0}}
    .blog-hero{{background:linear-gradient(135deg,#0d1117 0%,#0f1923 60%,#0a0b0f 100%);border-bottom:1px solid #1e2535;padding:100px 24px 60px;text-align:center}}
    .blog-hero .eyebrow{{font-size:.74rem;font-weight:700;letter-spacing:.16em;text-transform:uppercase;color:#00d4ff;margin-bottom:14px}}
    .blog-hero h1{{font-size:clamp(1.9rem,5vw,3.1rem);font-weight:800;color:#f0f4ff;margin:0 0 14px;letter-spacing:-.022em;line-height:1.15}}
    .blog-hero h1 span{{color:#00d4ff}}
    .blog-hero .sub{{font-size:1rem;color:#6b7a99;max-width:540px;margin:0 auto;line-height:1.7}}
    .blog-hero .pill{{display:inline-block;margin-top:20px;padding:6px 18px;border-radius:20px;background:#00d4ff12;border:1px solid #00d4ff30;color:#00d4ff;font-size:.78rem;font-weight:600}}
    .filters{{display:flex;flex-wrap:wrap;gap:10px;justify-content:center;padding:36px 24px 0}}
    .fbtn{{padding:8px 18px;border-radius:6px;border:1px solid #2a3245;background:transparent;color:#8a94b0;cursor:pointer;font-size:.82rem;font-weight:500;transition:all .2s}}
    .fbtn:hover,.fbtn.active{{background:#00d4ff12;border-color:#00d4ff50;color:#00d4ff}}
    .grid{{max-width:1200px;margin:40px auto 80px;padding:0 24px;display:grid;grid-template-columns:repeat(auto-fill,minmax(310px,1fr));gap:24px}}
    .card{{background:#0f1420;border:1px solid #1e2535;border-radius:10px;padding:26px;display:flex;flex-direction:column;transition:border-color .2s,transform .2s}}
    .card:hover{{border-color:#00d4ff40;transform:translateY(-3px)}}
    .card.hidden{{display:none}}
    .card-badge{{font-size:.7rem;font-weight:700;letter-spacing:.11em;text-transform:uppercase;color:#00d4ff;background:#00d4ff10;border:1px solid #00d4ff30;border-radius:4px;padding:3px 9px;display:inline-block;width:fit-content;margin-bottom:14px}}
    .card-title{{font-size:.97rem;font-weight:600;color:#e8edf8;line-height:1.45;margin:0 0 12px;flex-grow:1}}
    .card-snippet{{font-size:.85rem;color:#6b7a99;line-height:1.65;margin:0 0 18px}}
    .card-footer{{display:flex;justify-content:space-between;align-items:center;border-top:1px solid #1e2535;padding-top:14px;margin-top:auto}}
    .card-meta{{font-size:.74rem;color:#4a5568}}
    .card-meta em{{font-style:normal;color:#2e7d5e}}
    .card-read{{font-size:.82rem;font-weight:600;color:#00d4ff;text-decoration:none;transition:opacity .2s}}
    .card-read:hover{{opacity:.65}}
    .empty{{text-align:center;color:#4a5568;padding:64px 0;grid-column:1/-1}}
    @media(max-width:600px){{.grid{{grid-template-columns:1fr}}}}
  </style>
</head>
<body>
  <nav class="navbar"><div class="nav-container">
    <a href="/index.html" class="logo">Web3<span>Legals</span></a>
    <ul class="nav-links">
      <li><a href="/index.html">Home</a></li><li><a href="/about.html">About</a></li>
      <li><a href="/services.html">Services</a></li><li><a href="/blog/" class="active">Blog</a></li>
      <li><a href="/contact.html">Contact</a></li>
    </ul>
    <a href="/contact.html" class="cta-btn">Free Consultation</a>
    <button class="mobile-menu-btn" aria-label="Toggle menu">&#9776;</button>
  </div></nav>
  <div class="blog-hero">
    <div class="eyebrow">Legal Intelligence</div>
    <h1>Crypto &amp; Fintech <span>Law Blog</span></h1>
    <p class="sub">Original analysis on crypto regulation, fintech law, and Indian courts —
      by Rahul Pareek, Double Gold Medallist LLM, NLU India.</p>
    <div class="pill">{total} article{"s" if total!=1 else ""} published</div>
  </div>
  <div class="filters">
{btns_html}
  </div>
  <div class="grid" id="grid">
{cards_html}
  </div>
  <footer class="footer"><div class="footer-container">
    <div class="footer-brand">
      <a href="/index.html" class="logo">Web3<span>Legals</span></a>
      <p>India's leading legal firm for Web3, crypto, and fintech businesses.</p>
    </div>
    <div class="footer-links"><h4>Quick Links</h4>
      <ul><li><a href="/index.html">Home</a></li><li><a href="/about.html">About</a></li>
      <li><a href="/services.html">Services</a></li><li><a href="/blog/">Blog</a></li>
      <li><a href="/contact.html">Contact</a></li></ul>
    </div>
    <div class="footer-contact"><h4>Contact</h4>
      <p>Email: rahul@web3legals.com</p><p>Web3Legals | New Delhi, India</p>
    </div>
  </div>
  <div class="footer-bottom"><p>&copy; {year} Web3Legals. All rights reserved.</p></div>
  </footer>
  <script>
    (function(){{
      var btns=document.querySelectorAll('.fbtn');
      var cards=document.querySelectorAll('.card');
      btns.forEach(function(btn){{
        btn.addEventListener('click',function(){{
          btns.forEach(function(b){{b.classList.remove('active')}});
          btn.classList.add('active');
          var f=btn.getAttribute('data-filter');
          cards.forEach(function(card){{
            card.classList.toggle('hidden',f!=='all'&&card.getAttribute('data-cat')!==f);
          }});
        }});
      }});
    }})();
  </script>
  <script src="/js/main.js"></script>
</body></html>
"""

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print("="*60)
    print("  Web3Legals Crypto Radar — Phase 1 v4")
    print("="*60)
    print(f"  Run time  : {datetime.now(timezone.utc).isoformat()}")
    print(f"  AI route  : OpenRouter (free) → Gemini direct")
    print(f"  OR models : {len(OR_MODELS)} free models in chain")
    print(f"  Max       : {MAX_ARTICLES} articles/run")
    print("="*60)

    print("\n[1/5] Fetching RSS feeds…")
    candidates = []
    for cat, url in RSS_FEEDS:
        for item in fetch_rss(url, cat):
            item["aid"] = article_id(item["url"])
            candidates.append(item)
    seen_this = set()
    unique = []
    for c in candidates:
        if c["aid"] not in seen_this:
            seen_this.add(c["aid"])
            unique.append(c)
    print(f"  {len(candidates)} raw → {len(unique)} unique")

    print("\n[2/5] Checking seen articles…")
    seen_aids  = d1_check_seen([c["aid"] for c in unique])
    new_items  = [c for c in unique if c["aid"] not in seen_aids]
    to_process = new_items[:MAX_ARTICLES]
    print(f"  Seen: {len(seen_aids)} | New: {len(new_items)} | Processing: {len(to_process)}")
    if not to_process:
        print("No new articles. Exiting.")
        return

    print("\n[3/5] Generating articles…")
    os.makedirs(BLOG_DIR, exist_ok=True)
    new_meta = []
    for i, art in enumerate(to_process):
        print(f"\n  [{i+1}/{len(to_process)}] {art['title'][:65]}…")
        art_text = fetch_article_text(art["url"])
        analysis, has_ai = generate_analysis(art["title"], art["snippet"], art_text, art["category"])
        slug = slugify(art["title"])
        pub  = format_display_date(art.get("pubdate",""))
        path = os.path.join(BLOG_DIR, f"{slug}.html")
        with open(path,"w",encoding="utf-8") as f:
            f.write(article_html(art["title"], analysis, art["category"], art["url"], pub))
        print(f"    {'✓ AI' if has_ai else '⚠ fallback'} → {path}")
        new_meta.append({
            "aid": art["aid"], "title": art["title"], "slug": slug,
            "category": art["category"], "snippet": art["snippet"],
            "url": art["url"], "pub_display": pub, "has_ai": has_ai,
            "generated": datetime.now(timezone.utc).isoformat(),
        })
        if i < len(to_process)-1:
            print(f"    Waiting {DELAY_SECONDS}s…")
            time.sleep(DELAY_SECONDS)

    print("\n[4/5] Saving metadata…")
    d1_mark_seen([m["aid"] for m in new_meta])
    d1_upsert(new_meta)
    all_arts = d1_get_all()
    existing = {a["aid"] for a in all_arts}
    for m in new_meta:
        if m["aid"] not in existing:
            all_arts.insert(0, m)
    with open(".all_articles.json","w",encoding="utf-8") as f:
        json.dump(all_arts, f, indent=2, ensure_ascii=False)
    print(f"  Total: {len(all_arts)} articles")

    print("\n[5/5] Rebuilding blog/index.html…")
    with open(os.path.join(BLOG_DIR,"index.html"),"w",encoding="utf-8") as f:
        f.write(blog_index_html(all_arts))

    print("\n"+"="*60)
    print(f"  ✓ {len(new_meta)} new articles published")
    ai_count = sum(1 for m in new_meta if m["has_ai"])
    print(f"  ✓ {ai_count}/{len(new_meta)} with real AI analysis")
    print("="*60)

if __name__ == "__main__":
    main()
