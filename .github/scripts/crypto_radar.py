#!/usr/bin/env python3
"""
Web3Legals Crypto Legal Radar
Fetches crypto legal news via Google News RSS.
No API keys. Free forever. Works on GitHub Actions.
"""

import os
import re
import json
import hashlib
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

# ── CONFIG ───────────────────────────────────────────────────────────────────

# Google News RSS — free, no auth, always works on GitHub Actions
RSS_FEEDS = [
    "https://news.google.com/rss/search?q=crypto+regulation+law&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=cryptocurrency+SEC+CFTC&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=MiCA+DeFi+compliance&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=blockchain+legal+court+ruling&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=crypto+AML+KYC+FATF&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=DAO+token+securities+law&hl=en-US&gl=US&ceid=US:en",
]

KEYWORDS = [
    "regulation", "legal", "law", "sec", "cftc", "compliance", "court",
    "ruling", "ban", "license", "legislation", "enforcement", "sanction",
    "mica", "fatf", "aml", "kyc", "dao", "token", "securities", "lawsuit",
    "policy", "regulatory", "crypto law", "blockchain law", "defi", "nft",
]

CATEGORY_MAP = {
    "token":      ["token", "securities", "howey", "sto", "ico", "coin offering"],
    "dao":        ["dao", "governance", "decentralized autonomous"],
    "compliance": ["compliance", "aml", "kyc", "fatf", "travel rule", "sanction", "ofac"],
    "defi":       ["defi", "nft", "decentralized finance", "smart contract"],
    "startup":    ["startup", "incorporation", "entity", "formation", "vesting"],
}

BLOG_DIR   = Path(__file__).parent.parent / "blog"
SEEN_FILE  = Path(__file__).parent.parent / ".seen_articles.json"

# ── HELPERS ──────────────────────────────────────────────────────────────────

def load_seen():
    if SEEN_FILE.exists():
        try:
            return set(json.loads(SEEN_FILE.read_text()))
        except Exception:
            return set()
    return set()

def save_seen(seen):
    SEEN_FILE.write_text(json.dumps(list(seen), indent=2))

def slugify(text):
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    text = re.sub(r"^-+|-+$", "", text)
    return text[:80]

def article_id(url):
    return hashlib.md5(url.encode()).hexdigest()[:12]

def is_relevant(title, description=""):
    combined = (title + " " + description).lower()
    return any(kw in combined for kw in KEYWORDS)

def detect_category(title, description=""):
    combined = (title + " " + description).lower()
    for cat, terms in CATEGORY_MAP.items():
        if any(t in combined for t in terms):
            return cat
    return "compliance"

def category_badge(cat):
    return {
        "token":      ("badge-gold",  "Token Law"),
        "dao":        ("badge-teal",  "DAO Law"),
        "compliance": ("badge-white", "Compliance"),
        "defi":       ("badge-teal",  "DeFi & NFT"),
        "startup":    ("badge-gold",  "Startup Law"),
    }.get(cat, ("badge-white", "Crypto Law"))

def category_emoji(cat):
    return {"token": "🪙", "dao": "🏛", "compliance": "🛡", "defi": "🔗", "startup": "🚀"}.get(cat, "📋")

# ── RSS FETCH ─────────────────────────────────────────────────────────────────

def fetch_feed(url):
    articles = []
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; Web3LegalsBot/1.0)",
            "Accept": "application/rss+xml, application/xml, text/xml, */*",
        }
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read()
        root = ET.fromstring(raw)
        channel = root.find("channel")
        items = channel.findall("item") if channel else root.findall(".//item")
        for item in items[:20]:
            title = (item.findtext("title") or "").strip()
            link  = (item.findtext("link")  or "").strip()
            desc  = re.sub(r"<[^>]+>", "", item.findtext("description") or "").strip()
            if title and link and is_relevant(title, desc):
                articles.append({
                    "title":       title,
                    "url":         link,
                    "description": desc[:600],
                    "category":    detect_category(title, desc),
                })
    except Exception as e:
        print(f"  ⚠  Feed error {url[:60]}: {e}")
    return articles

# ── HTML TEMPLATES ────────────────────────────────────────────────────────────

NAV = """<nav class="nav" id="nav">
  <div class="nav-inner">
    <a href="../index.html" class="nav-logo"><div class="nav-logo-icon">W3</div><span>Web3<span class="text-gold">Legals</span></span></a>
    <ul class="nav-links">
      <li><a href="../index.html">Home</a></li>
      <li><a href="../services.html">Services</a></li>
      <li><a href="../about.html">About</a></li>
      <li><a href="../blog.html" class="active">Blog</a></li>
      <li><a href="../contact.html">Contact</a></li>
    </ul>
    <div class="nav-cta"><a href="../contact.html" class="btn btn-gold">Book a Call</a></div>
    <div class="nav-hamburger" id="hamburger"><span></span><span></span><span></span></div>
  </div>
</nav>
<div class="mobile-menu" id="mobileMenu">
  <a href="../index.html">Home</a><a href="../services.html">Services</a>
  <a href="../about.html">About</a><a href="../blog.html">Blog</a>
  <a href="../contact.html">Contact</a>
  <a href="../contact.html" class="btn btn-gold" style="margin-top:16px">Book a Free Call</a>
</div>"""

FOOTER = """<footer class="footer">
  <div class="container">
    <div class="footer-grid">
      <div class="footer-brand">
        <a href="../index.html" class="nav-logo" style="display:inline-flex">
          <div class="nav-logo-icon">W3</div>
          <span>Web3<span class="text-gold">Legals</span></span>
        </a>
        <p>Legal clarity for the decentralized world.</p>
        <div class="footer-social">
          <a href="https://linkedin.com/in/rahulpareek2302" class="social-link">in</a>
          <a href="#" class="social-link">𝕏</a>
        </div>
      </div>
      <div class="footer-col"><h4>Services</h4><ul class="footer-links">
        <li><a href="../services.html">Token Advisory</a></li>
        <li><a href="../services.html">DAO Wrappers</a></li>
        <li><a href="../services.html">KYC/AML</a></li>
      </ul></div>
      <div class="footer-col"><h4>Company</h4><ul class="footer-links">
        <li><a href="../about.html">About Rahul</a></li>
        <li><a href="../blog.html">Blog</a></li>
        <li><a href="../contact.html">Contact</a></li>
      </ul></div>
      <div class="footer-col"><h4>Contact</h4><ul class="footer-links">
        <li><a href="mailto:rahul@web3legals.com">rahul@web3legals.com</a></li>
        <li><a href="../contact.html">Book a Call</a></li>
      </ul></div>
    </div>
    <div class="footer-bottom">
      <span>© 2026 Web3Legals. Founded by <a href="../about.html">Rahul Pareek</a>.</span>
      <span>Disclaimer: Informational only — not legal advice.</span>
    </div>
  </div>
</footer>"""

def build_article_html(article, slug):
    cat         = article["category"]
    badge_cls, badge_lbl = category_badge(cat)
    emoji       = category_emoji(cat)
    date_str    = datetime.now().strftime("%B %d, %Y")
    title       = article["title"]
    description = article["description"]
    source_url  = article["url"]

    # Turn description into paragraph(s)
    sentences = re.split(r'(?<=[.!?])\s+', description)
    paras = []
    buf = []
    for s in sentences:
        buf.append(s)
        if len(buf) >= 3:
            paras.append(" ".join(buf))
            buf = []
    if buf:
        paras.append(" ".join(buf))
    body_html = "\n".join(f"        <p>{p.strip()}</p>" for p in paras if p.strip())
    if not body_html:
        body_html = f"        <p>{description}</p>"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} — Web3Legals</title>
<meta name="description" content="{description[:160]}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="../css/style.css">
</head>
<body>

{NAV}

<section class="page-hero">
  <div class="page-hero-bg"></div>
  <div class="container" style="position:relative;z-index:2">
    <div class="eyebrow">
      <a href="../blog.html" style="color:inherit;text-decoration:none">← Back to Blog</a>
    </div>
    <h1 style="font-size:clamp(1.6rem,4vw,2.4rem);max-width:800px;line-height:1.3">{title}</h1>
    <div style="display:flex;gap:16px;align-items:center;flex-wrap:wrap;margin-top:16px">
      <span class="badge {badge_cls}">{badge_lbl}</span>
      <span style="color:var(--gray);font-size:0.875rem">{date_str}</span>
      <span style="color:var(--gray);font-size:0.875rem">3 min read</span>
    </div>
  </div>
</section>

<section class="section" style="padding-top:40px">
  <div class="container">
    <div style="max-width:760px;margin:0 auto">

      <div style="font-size:3.5rem;text-align:center;margin-bottom:32px">{emoji}</div>

      <div style="font-size:1.05rem;line-height:1.85;color:var(--gray-light)">
{body_html}

        <div style="margin:40px 0;padding:24px;border-left:3px solid var(--gold);background:rgba(212,175,55,0.05);border-radius:0 var(--radius) var(--radius) 0">
          <p style="margin:0;font-size:0.875rem;color:var(--gray)">
            <strong style="color:var(--gold)">Source:</strong>
            This article is based on external reporting.
            <a href="{source_url}" target="_blank" rel="noopener noreferrer" style="color:var(--gold)">Read the original article →</a>
          </p>
        </div>

        <div style="margin:48px 0;padding:32px;background:rgba(255,255,255,0.04);border:1px solid var(--border2);border-radius:var(--radius);text-align:center">
          <p style="font-size:0.9rem;color:var(--gray);margin-bottom:20px">
            <strong style="color:var(--white)">Need legal clarity on this?</strong><br>
            Rahul Pareek helps Web3 founders navigate crypto regulation — token compliance, DAO structuring, and more.
          </p>
          <a href="../contact.html" class="btn btn-gold">Book a Free Consultation →</a>
        </div>
      </div>

      <div style="margin-top:48px;padding-top:32px;border-top:1px solid var(--border)">
        <a href="../blog.html" class="btn" style="border:1px solid var(--border2)">← All Articles</a>
      </div>

    </div>
  </div>
</section>

{FOOTER}

<button class="back-top" id="backTop" aria-label="Back to top">↑</button>
<script src="../js/main.js"></script>
</body>
</html>"""

def build_card_html(article, slug):
    cat = article["category"]
    badge_cls, badge_lbl = category_badge(cat)
    emoji = category_emoji(cat)
    snippet = article["description"][:180]
    if len(article["description"]) > 180:
        snippet += "..."
    title = article["title"]
    return f"""      <div class="blog-card fade-up" data-category="{cat}">
        <div class="blog-card-image">{emoji}</div>
        <div class="blog-card-body">
          <div class="blog-card-meta"><span class="badge {badge_cls}">{badge_lbl}</span><span>3 min read</span></div>
          <h3><a href="blog/{slug}.html">{title}</a></h3>
          <p>{snippet}</p>
          <a href="blog/{slug}.html" class="blog-read-more">Read article <span>→</span></a>
        </div>
      </div>"""

# ── BLOG INDEX UPDATE ─────────────────────────────────────────────────────────

def update_blog_index(cards_html):
    """Replace the loading spinner in #cmsArticles with the latest article cards."""
    blog_index = Path(__file__).parent.parent / "blog.html"
    if not blog_index.exists():
        print("  ⚠  blog.html not found — skipping index update")
        return

    content = blog_index.read_text(encoding="utf-8")

    # The section we want to replace starts at cmsArticles div, ends before staticArticles
    start_marker = '<div class="grid-3" id="cmsArticles"'
    end_marker   = '\n\n    <!-- STATIC ARTICLES'

    start = content.find(start_marker)
    end   = content.find(end_marker, start)

    if start == -1 or end == -1:
        print("  ⚠  Could not locate #cmsArticles in blog.html")
        return

    # Find the closing </div> of the cmsArticles block
    div_end = content.find("</div>", end - 10)  # close tag just before static articles comment
    # Actually find the </div> that closes the cmsArticles grid
    depth = 0
    i = start
    while i < len(content):
        if content[i:i+4] == "<div":
            depth += 1
        elif content[i:i+6] == "</div>":
            depth -= 1
            if depth == 0:
                div_end = i + 6
                break
        i += 1

    new_block = f"""<div class="grid-3" id="cmsArticles" style="margin-bottom:40px">
{cards_html}
    </div>"""

    content = content[:start] + new_block + content[div_end:]
    blog_index.write_text(content, encoding="utf-8")
    n = cards_html.count('blog-card fade-up')
    print(f"  ✅ blog.html updated with {n} article cards")

# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    print("🌐 Web3Legals — Crypto Legal Radar Starting...")
    BLOG_DIR.mkdir(exist_ok=True)

    seen = load_seen()
    new_articles = []

    for feed_url in RSS_FEEDS:
        print(f"  📡 {feed_url[:70]}")
        for a in fetch_feed(feed_url):
            aid = article_id(a["url"])
            if aid not in seen:
                new_articles.append((aid, a))

    # Deduplicate by title similarity
    seen_titles = set()
    deduped = []
    for aid, a in new_articles:
        key = slugify(a["title"])[:40]
        if key not in seen_titles:
            seen_titles.add(key)
            deduped.append((aid, a))

    print(f"\n📋 {len(deduped)} new relevant articles found")

    if not deduped:
        print("✅ Nothing new today. Done.")
        return

    published_cards = []

    for aid, article in deduped[:12]:  # max 12 per run
        slug = slugify(article["title"])
        filepath = BLOG_DIR / f"{slug}.html"

        if filepath.exists():
            seen.add(aid)
            continue

        try:
            filepath.write_text(build_article_html(article, slug), encoding="utf-8")
            seen.add(aid)
            published_cards.append(build_card_html(article, slug))
            print(f"  ✅ {article['title'][:65]}")
        except Exception as e:
            print(f"  ❌ {article['title'][:40]} — {e}")

    if published_cards:
        update_blog_index("\n".join(published_cards))

    save_seen(seen)
    print(f"\n🎉 Published {len(published_cards)} articles. Cloudflare Pages will deploy automatically.")

if __name__ == "__main__":
    main()
