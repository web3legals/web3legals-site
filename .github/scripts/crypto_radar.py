#!/usr/bin/env python3
"""
crypto_radar.py — Web3Legals Auto-Publishing Blog System
Fetches crypto/fintech/India legal news, generates analysis via Gemini, publishes static HTML.
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
import xml.etree.ElementTree as ET

import google.generativeai as genai

# ── Config ──────────────────────────────────────────────────────────────────

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
GEMINI_MODEL   = "gemini-2.0-flash"
MAX_ARTICLES   = 12
DELAY_SECONDS  = 3
SEEN_FILE      = ".seen_articles.json"
ALL_FILE       = ".all_articles.json"
BLOG_DIR       = "blog"

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
    "crypto":      {"label": "Crypto Law",       "emoji": "⚖️",  "badge": "CRYPTO"},
    "fintech":     {"label": "Fintech",           "emoji": "🏦",  "badge": "FINTECH"},
    "india-legal": {"label": "India Courts",      "emoji": "🏛️",  "badge": "INDIA"},
    "compliance":  {"label": "Compliance",        "emoji": "🔍",  "badge": "AML/KYC"},
    "dao":         {"label": "DAO & Governance",  "emoji": "🗳️",  "badge": "DAO"},
    "token":       {"label": "Token Law",         "emoji": "🪙",  "badge": "TOKEN"},
}

# ── Helpers ──────────────────────────────────────────────────────────────────

def load_json(path, default):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def article_id(url):
    return hashlib.md5(url.encode()).hexdigest()[:12]

def slugify(title):
    slug = re.sub(r"[^\w\s-]", "", title.lower())
    slug = re.sub(r"[\s_]+", "-", slug).strip("-")
    return slug[:80]

def fetch_rss(url, category):
    """Fetch and parse a Google News RSS feed."""
    items = []
    try:
        req = Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; Web3Legals/1.0)"})
        with urlopen(req, timeout=15) as resp:
            xml_data = resp.read()
        root = ET.fromstring(xml_data)
        channel = root.find("channel")
        if channel is None:
            return items
        for item in channel.findall("item"):
            title_el = item.find("title")
            link_el  = item.find("link")
            desc_el  = item.find("description")
            pubdate_el = item.find("pubDate")
            if title_el is None or link_el is None:
                continue
            title   = (title_el.text or "").strip()
            link    = (link_el.text or "").strip()
            snippet = re.sub(r"<[^>]+>", "", (desc_el.text or "") if desc_el is not None else "").strip()
            pubdate = (pubdate_el.text or "").strip() if pubdate_el is not None else ""
            # Filter low-quality titles
            if len(title) < 10 or title.lower() in ("", "untitled"):
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
    """Try to fetch full article text via newspaper3k."""
    try:
        from newspaper import Article
        art = Article(url)
        art.download()
        art.parse()
        text = art.text.strip()
        return text[:3000] if text else ""
    except Exception:
        return ""

def generate_analysis(title, snippet, article_text, category):
    """Call Gemini to write a 400-word legal analysis."""
    cat_label = CATEGORY_META.get(category, {}).get("label", category)
    context = article_text if article_text else snippet
    prompt = textwrap.dedent(f"""
        You are Rahul Pareek, founder of Web3Legals and a Double Gold Medallist LLM from National Law University India.
        You are a leading expert in crypto law, fintech regulation, and Indian judiciary matters.

        Write a 400-word original legal analysis of the following news for Web3Legals.com.
        Category: {cat_label}

        News Title: {title}

        Context:
        {context}

        Requirements:
        - Write in first person as Rahul Pareek
        - Open with a sharp legal observation, not a generic intro
        - Cite relevant laws, regulations, or court precedents where applicable (SEC, CFTC, MiCA, RBI, SEBI, IPC, Indian IT Act, etc.)
        - Explain the practical implications for founders, investors, and legal teams
        - End with a concrete takeaway or recommended action
        - Exactly 400 words, no markdown, no bullet points, plain paragraphs only
        - Do NOT repeat the news title verbatim in the first sentence
    """).strip()

    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(GEMINI_MODEL)
    response = model.generate_content(prompt)
    return response.text.strip()

def format_display_date(pubdate_str):
    """Parse RSS pubDate into a readable string."""
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

# ── HTML Templates ────────────────────────────────────────────────────────────

def article_html(title, analysis, category, source_url, pub_display, slug):
    cat = CATEGORY_META.get(category, CATEGORY_META["crypto"])
    paragraphs = "\n".join(
        f'      <p>{p.strip()}</p>'
        for p in analysis.split("\n") if p.strip()
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{title} | Web3Legals</title>
  <meta name="description" content="{title[:155]}" />
  <link rel="stylesheet" href="/css/style.css" />
  <style>
    /* ── Article-page overrides ── */
    body {{ background: #0a0b0f; color: #d4d8e2; font-family: 'Inter', sans-serif; margin: 0; }}
    .w3l-article-hero {{
      background: linear-gradient(135deg, #0d1117 0%, #0f1923 50%, #0a0b0f 100%);
      border-bottom: 1px solid #1e2535;
      padding: 80px 24px 48px;
      text-align: center;
    }}
    .w3l-article-hero .back-link {{
      display: inline-flex; align-items: center; gap: 6px;
      color: #00d4ff; text-decoration: none; font-size: 0.85rem;
      font-weight: 500; letter-spacing: 0.05em; text-transform: uppercase;
      margin-bottom: 28px; transition: opacity .2s;
    }}
    .w3l-article-hero .back-link:hover {{ opacity: .7; }}
    .w3l-article-hero .badge {{
      display: inline-block; padding: 4px 12px; border-radius: 4px;
      background: #00d4ff22; color: #00d4ff; font-size: 0.72rem;
      font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase;
      border: 1px solid #00d4ff44; margin-bottom: 20px;
    }}
    .w3l-article-hero h1 {{
      font-size: clamp(1.5rem, 4vw, 2.4rem); font-weight: 700;
      color: #f0f4ff; line-height: 1.3; max-width: 800px;
      margin: 0 auto 20px; letter-spacing: -0.01em;
    }}
    .w3l-article-hero .meta {{
      font-size: 0.85rem; color: #6b7a99;
    }}
    .w3l-article-hero .meta span {{ margin: 0 8px; }}
    .w3l-article-body {{
      max-width: 760px; margin: 0 auto; padding: 56px 24px 80px;
    }}
    .w3l-article-body p {{
      font-size: 1.05rem; line-height: 1.85; color: #b8c0d4;
      margin: 0 0 22px;
    }}
    .w3l-article-body p:first-child::first-letter {{
      font-size: 3.2em; font-weight: 700; color: #00d4ff;
      float: left; line-height: 0.75; margin: 6px 12px 0 0;
    }}
    .w3l-source-bar {{
      max-width: 760px; margin: 0 auto 48px; padding: 0 24px;
      display: flex; align-items: center; gap: 12px;
      border-top: 1px solid #1e2535; padding-top: 24px;
    }}
    .w3l-source-bar span {{ font-size: 0.8rem; color: #6b7a99; }}
    .w3l-source-bar a {{
      color: #00d4ff; font-size: 0.8rem; text-decoration: none;
      word-break: break-all;
    }}
    .w3l-source-bar a:hover {{ text-decoration: underline; }}
    .w3l-cta-bar {{
      background: linear-gradient(135deg, #00d4ff11, #0066ff11);
      border: 1px solid #00d4ff33; border-radius: 12px;
      max-width: 760px; margin: 0 auto 80px; padding: 36px 32px;
      text-align: center;
    }}
    .w3l-cta-bar h3 {{
      color: #f0f4ff; font-size: 1.2rem; margin: 0 0 8px; font-weight: 600;
    }}
    .w3l-cta-bar p {{
      color: #6b7a99; font-size: 0.9rem; margin: 0 0 20px;
    }}
    .w3l-cta-bar a {{
      display: inline-block; padding: 12px 28px; border-radius: 6px;
      background: linear-gradient(135deg, #00d4ff, #0066ff);
      color: #fff; font-weight: 600; text-decoration: none;
      font-size: 0.9rem; transition: opacity .2s;
    }}
    .w3l-cta-bar a:hover {{ opacity: .85; }}
    /* Reuse site nav/footer via main.js */
  </style>
</head>
<body>
  <!-- NAV (matching existing site structure) -->
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

  <div class="w3l-article-hero">
    <a href="/blog/" class="back-link">← Back to Blog</a>
    <div class="badge">{cat['emoji']} {cat['badge']}</div>
    <h1>{title}</h1>
    <p class="meta">
      <span>By Rahul Pareek</span>·
      <span>{pub_display}</span>·
      <span>{cat['label']}</span>
    </p>
  </div>

  <div class="w3l-article-body">
{paragraphs}
  </div>

  <div class="w3l-source-bar">
    <span>Original source:</span>
    <a href="{source_url}" target="_blank" rel="noopener noreferrer">{source_url[:90]}{"…" if len(source_url) > 90 else ""}</a>
  </div>

  <div class="w3l-cta-bar">
    <h3>Need Legal Clarity on This?</h3>
    <p>Get tailored advice from India's leading Web3 & fintech legal expert.</p>
    <a href="/contact.html">Book a Free Consultation</a>
  </div>

  <!-- FOOTER -->
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
      <p>&copy; {datetime.now().year} Web3Legals. All rights reserved.</p>
    </div>
  </footer>

  <script src="/js/main.js"></script>
</body>
</html>
"""

def blog_index_html(all_articles):
    """Build blog/index.html as fully static HTML with filter buttons."""
    now_year = datetime.now().year

    # Build card HTML for each article
    cards_by_cat = {"all": []}
    for cat_key in CATEGORY_META:
        cards_by_cat[cat_key] = []

    for art in all_articles:
        cat   = art.get("category", "crypto")
        meta  = CATEGORY_META.get(cat, CATEGORY_META["crypto"])
        slug  = art["slug"]
        title = art["title"]
        snippet = (art.get("snippet") or "")[:160]
        pub   = art.get("pub_display", "")
        card_html = f"""        <div class="w3l-card" data-cat="{cat}">
          <div class="w3l-card-badge">{meta['emoji']} {meta['badge']}</div>
          <h3 class="w3l-card-title">{title}</h3>
          <p class="w3l-card-snippet">{snippet}{"…" if len(snippet) == 160 else ""}</p>
          <div class="w3l-card-footer">
            <span class="w3l-card-date">{pub}</span>
            <a class="w3l-card-read" href="/blog/{slug}.html">Read article →</a>
          </div>
        </div>"""
        cards_by_cat["all"].append(card_html)
        if cat in cards_by_cat:
            cards_by_cat[cat].append(card_html)

    filter_buttons = [
        ("all",         "All Articles"),
        ("crypto",      "Crypto Law"),
        ("fintech",     "Fintech"),
        ("india-legal", "India Courts"),
        ("dao",         "DAO & Governance"),
        ("compliance",  "Compliance"),
        ("token",       "Token Law"),
    ]

    buttons_html = "\n".join(
        f'      <button class="w3l-filter-btn{" active" if k == "all" else ""}" data-filter="{k}">{label}</button>'
        for k, label in filter_buttons
    )

    all_cards_html = "\n".join(cards_by_cat["all"]) if cards_by_cat["all"] else \
        '        <p class="w3l-empty">No articles yet. Check back soon.</p>'

    total = len(all_articles)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Legal Intelligence Blog | Web3Legals</title>
  <meta name="description" content="Expert legal analysis on crypto regulation, fintech law, and Indian courts — by Rahul Pareek, Web3Legals." />
  <link rel="stylesheet" href="/css/style.css" />
  <style>
    body {{ background: #0a0b0f; color: #d4d8e2; font-family: 'Inter', sans-serif; margin: 0; }}

    .w3l-blog-hero {{
      background: linear-gradient(135deg, #0d1117 0%, #0f1923 60%, #0a0b0f 100%);
      border-bottom: 1px solid #1e2535;
      padding: 100px 24px 60px;
      text-align: center;
    }}
    .w3l-blog-hero .eyebrow {{
      font-size: 0.75rem; font-weight: 700; letter-spacing: 0.15em;
      text-transform: uppercase; color: #00d4ff; margin-bottom: 16px;
    }}
    .w3l-blog-hero h1 {{
      font-size: clamp(2rem, 5vw, 3.2rem); font-weight: 800;
      color: #f0f4ff; margin: 0 0 16px; letter-spacing: -0.02em;
      line-height: 1.15;
    }}
    .w3l-blog-hero h1 span {{ color: #00d4ff; }}
    .w3l-blog-hero p {{
      font-size: 1.05rem; color: #6b7a99; max-width: 560px;
      margin: 0 auto; line-height: 1.7;
    }}
    .w3l-blog-hero .count-pill {{
      display: inline-block; margin-top: 20px; padding: 6px 16px;
      border-radius: 20px; background: #00d4ff15; border: 1px solid #00d4ff33;
      color: #00d4ff; font-size: 0.8rem; font-weight: 600;
    }}

    .w3l-filters {{
      display: flex; flex-wrap: wrap; gap: 10px;
      justify-content: center; padding: 36px 24px 0;
    }}
    .w3l-filter-btn {{
      padding: 8px 18px; border-radius: 6px; border: 1px solid #2a3245;
      background: transparent; color: #8a94b0; cursor: pointer;
      font-size: 0.82rem; font-weight: 500; transition: all .2s;
    }}
    .w3l-filter-btn:hover,
    .w3l-filter-btn.active {{
      background: #00d4ff15; border-color: #00d4ff55; color: #00d4ff;
    }}

    .w3l-grid {{
      max-width: 1200px; margin: 40px auto 80px;
      padding: 0 24px;
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
      gap: 24px;
    }}
    .w3l-card {{
      background: #0f1420; border: 1px solid #1e2535; border-radius: 10px;
      padding: 28px; display: flex; flex-direction: column;
      transition: border-color .2s, transform .2s;
    }}
    .w3l-card:hover {{ border-color: #00d4ff44; transform: translateY(-2px); }}
    .w3l-card.hidden {{ display: none; }}
    .w3l-card-badge {{
      font-size: 0.72rem; font-weight: 700; letter-spacing: 0.1em;
      text-transform: uppercase; color: #00d4ff;
      background: #00d4ff12; border: 1px solid #00d4ff33;
      border-radius: 4px; padding: 3px 9px; display: inline-block;
      width: fit-content; margin-bottom: 14px;
    }}
    .w3l-card-title {{
      font-size: 1rem; font-weight: 600; color: #e8edf8;
      line-height: 1.45; margin: 0 0 12px; flex-grow: 1;
    }}
    .w3l-card-snippet {{
      font-size: 0.87rem; color: #6b7a99; line-height: 1.6;
      margin: 0 0 20px;
    }}
    .w3l-card-footer {{
      display: flex; justify-content: space-between; align-items: center;
      border-top: 1px solid #1e2535; padding-top: 16px; margin-top: auto;
    }}
    .w3l-card-date {{ font-size: 0.78rem; color: #4a5568; }}
    .w3l-card-read {{
      font-size: 0.82rem; font-weight: 600; color: #00d4ff;
      text-decoration: none; transition: opacity .2s;
    }}
    .w3l-card-read:hover {{ opacity: .7; }}
    .w3l-empty {{ text-align: center; color: #4a5568; padding: 60px 0; grid-column: 1/-1; }}

    @media (max-width: 600px) {{
      .w3l-grid {{ grid-template-columns: 1fr; }}
      .w3l-filters {{ gap: 8px; }}
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

  <div class="w3l-blog-hero">
    <div class="eyebrow">Legal Intelligence</div>
    <h1>Crypto &amp; Fintech <span>Law Blog</span></h1>
    <p>Original analysis on crypto regulation, fintech law, and Indian courts — by Rahul Pareek, Double Gold Medallist LLM, NLU India.</p>
    <div class="count-pill">{total} article{"s" if total != 1 else ""} published</div>
  </div>

  <div class="w3l-filters">
{buttons_html}
  </div>

  <div class="w3l-grid" id="w3l-grid">
{all_cards_html}
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
      <p>&copy; {now_year} Web3Legals. All rights reserved.</p>
    </div>
  </footer>

  <script>
    // Pure static filter — no fetch, no external calls
    (function() {{
      var btns  = document.querySelectorAll('.w3l-filter-btn');
      var cards = document.querySelectorAll('.w3l-card');
      btns.forEach(function(btn) {{
        btn.addEventListener('click', function() {{
          btns.forEach(function(b) {{ b.classList.remove('active'); }});
          btn.classList.add('active');
          var f = btn.getAttribute('data-filter');
          cards.forEach(function(card) {{
            if (f === 'all' || card.getAttribute('data-cat') === f) {{
              card.classList.remove('hidden');
            }} else {{
              card.classList.add('hidden');
            }}
          }});
        }});
      }});
    }})();
  </script>
  <script src="/js/main.js"></script>
</body>
</html>
"""

# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("=== Web3Legals Crypto Radar ===")
    print(f"Run time: {datetime.now(timezone.utc).isoformat()}")

    # Load state
    seen     = set(load_json(SEEN_FILE, []))
    all_arts = load_json(ALL_FILE, [])
    print(f"Previously seen: {len(seen)} | Stored articles: {len(all_arts)}")

    # Collect new articles from RSS
    candidates = []
    for category, feed_url in RSS_FEEDS:
        print(f"  Fetching [{category}]: {feed_url[:60]}…")
        items = fetch_rss(feed_url, category)
        for item in items:
            aid = article_id(item["url"])
            if aid not in seen:
                item["aid"] = aid
                candidates.append(item)

    # Deduplicate by aid within this batch
    seen_this_run = set()
    unique_candidates = []
    for c in candidates:
        if c["aid"] not in seen_this_run:
            seen_this_run.add(c["aid"])
            unique_candidates.append(c)

    print(f"New candidates this run: {len(unique_candidates)}")
    to_process = unique_candidates[:MAX_ARTICLES]
    print(f"Processing up to {MAX_ARTICLES}: will handle {len(to_process)}")

    os.makedirs(BLOG_DIR, exist_ok=True)
    new_count = 0

    for i, art in enumerate(to_process):
        print(f"\n[{i+1}/{len(to_process)}] {art['title'][:70]}")

        # Fetch article full text
        article_text = fetch_article_text(art["url"])
        if article_text:
            print(f"  Full text fetched: {len(article_text)} chars")
        else:
            print("  Using RSS snippet as context")

        # Generate analysis via Gemini
        analysis = ""
        try:
            analysis = generate_analysis(
                art["title"], art["snippet"], article_text, art["category"]
            )
            print(f"  Gemini: {len(analysis)} chars generated")
        except Exception as e:
            print(f"  Gemini failed ({e}), using fallback snippet")
            analysis = (
                f"The following news item has emerged from the {art['category']} space: "
                f"{art['title']}. {art['snippet']} "
                "This development warrants careful attention from legal practitioners, "
                "founders, and compliance teams operating in this sector. "
                "Web3Legals will provide a detailed analysis shortly. "
                "For immediate legal guidance, please reach out via our contact page."
            )

        slug       = slugify(art["title"])
        pub_display = format_display_date(art.get("pubdate", ""))

        # Save article HTML
        html = article_html(
            title       = art["title"],
            analysis    = analysis,
            category    = art["category"],
            source_url  = art["url"],
            pub_display = pub_display,
            slug        = slug,
        )
        out_path = os.path.join(BLOG_DIR, f"{slug}.html")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"  Saved: {out_path}")

        # Update metadata store
        meta_entry = {
            "aid":         art["aid"],
            "title":       art["title"],
            "slug":        slug,
            "category":    art["category"],
            "snippet":     art["snippet"],
            "url":         art["url"],
            "pub_display": pub_display,
            "generated":   datetime.now(timezone.utc).isoformat(),
        }
        all_arts.insert(0, meta_entry)  # newest first
        seen.add(art["aid"])
        new_count += 1

        # Delay to avoid Gemini rate-limits
        if i < len(to_process) - 1:
            print(f"  Waiting {DELAY_SECONDS}s…")
            time.sleep(DELAY_SECONDS)

    print(f"\nNew articles written: {new_count}")

    # Rebuild blog/index.html
    index_html = blog_index_html(all_arts)
    index_path = os.path.join(BLOG_DIR, "index.html")
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(index_html)
    print(f"Rebuilt: {index_path} ({len(all_arts)} total articles)")

    # Persist state
    save_json(SEEN_FILE, list(seen))
    save_json(ALL_FILE, all_arts)
    print("State saved.")
    print("=== Done ===")

if __name__ == "__main__":
    main()
