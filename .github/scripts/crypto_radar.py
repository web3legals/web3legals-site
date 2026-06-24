#!/usr/bin/env python3
import os
import re
import json
import time
import requests
import feedparser
from datetime import datetime, timezone
from slugify import slugify

# ─────────────────────────────────────────────
#  LLM PROVIDER CONFIG  (all free tiers)
# ─────────────────────────────────────────────
GEMINI_API_KEY   = os.environ.get("GEMINI_API_KEY", "")
GROQ_API_KEY     = os.environ.get("GROQ_API_KEY", "")       # free at console.groq.com
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "") # free tier at console.anthropic.com

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
GROQ_URL   = "https://api.groq.com/openai/v1/chat/completions"
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"

# ─────────────────────────────────────────────
#  RSS + KEYWORDS  (unchanged)
# ─────────────────────────────────────────────
RSS_FEEDS = [
    "https://cointelegraph.com/rss/tag/regulation",
    "https://decrypt.co/feed",
    "https://www.coindesk.com/arc/outboundfeeds/rss/?outputType=xml",
    "https://cryptoslate.com/feed/",
    "https://bitcoinmagazine.com/.rss/full/",
    "https://inc42.com/tag/cryptocurrency/feed/",
    "https://entrackr.com/tag/crypto/feed/",
]

LEGAL_KEYWORDS = [
    "regulation", "regulatory", "sec ", "cftc", "sebi", "rbi", "fiu",
    "lawsuit", "enforcement", "ban", "legal", "court", "ruling", "law",
    "compliance", "mica", "fatf", "aml", "kyc", "tax", "cbdc",
    "bill", "legislation", "policy", "sanction", "fine", "penalty",
    "crypto law", "blockchain law", "token", "dao", "defi regulation",
    "nft law", "web3 law", "india crypto", "crypto india"
]

PUBLISHED_FILE   = ".github/scripts/published_urls.json"
FAILED_QUEUE_FILE = ".github/scripts/failed_queue.json"  # NEW: retry queue

# ─────────────────────────────────────────────
#  PUBLISHED / FAILED QUEUE HELPERS
# ─────────────────────────────────────────────
def load_published():
    try:
        with open(PUBLISHED_FILE, 'r') as f:
            return set(json.load(f))
    except:
        return set()

def save_published(published):
    os.makedirs(os.path.dirname(PUBLISHED_FILE), exist_ok=True)
    with open(PUBLISHED_FILE, 'w') as f:
        json.dump(list(published), f, indent=2)

def load_failed_queue():
    try:
        with open(FAILED_QUEUE_FILE, 'r') as f:
            return json.load(f)
    except:
        return []

def save_failed_queue(queue):
    os.makedirs(os.path.dirname(FAILED_QUEUE_FILE), exist_ok=True)
    with open(FAILED_QUEUE_FILE, 'w') as f:
        json.dump(queue, f, indent=2)

def add_to_failed_queue(news_item):
    queue = load_failed_queue()
    urls = [q['url'] for q in queue]
    if news_item['url'] not in urls:
        news_item['queued_at'] = datetime.now(timezone.utc).isoformat()
        queue.append(news_item)
        save_failed_queue(queue)
        print(f"📥 Added to retry queue: {news_item['title']}")

def remove_from_failed_queue(url):
    queue = load_failed_queue()
    queue = [q for q in queue if q['url'] != url]
    save_failed_queue(queue)

# ─────────────────────────────────────────────
#  MULTI-LLM ROUTER  (Gemini → Groq → Claude)
# ─────────────────────────────────────────────
def _call_gemini(prompt, retries=3):
    if not GEMINI_API_KEY:
        return None
    for attempt in range(retries):
        try:
            response = requests.post(
                f"{GEMINI_URL}?key={GEMINI_API_KEY}",
                headers={"Content-Type": "application/json"},
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"temperature": 0.5, "maxOutputTokens": 3000}
                },
                timeout=90
            )
            response.raise_for_status()
            return response.json()['candidates'][0]['content']['parts'][0]['text'].strip()
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response else 0
            if status in [429, 503] and attempt < retries - 1:
                wait = 15 * (2 ** attempt)   # 15s, 30s, 60s
                print(f"  Gemini {status} — retrying in {wait}s...")
                time.sleep(wait)
            else:
                print(f"  Gemini failed ({status})")
                return None
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(10)
            else:
                print(f"  Gemini error: {e}")
                return None
    return None

def _call_groq(prompt):
    if not GROQ_API_KEY:
        return None
    try:
        response = requests.post(
            GROQ_URL,
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "llama-3.3-70b-versatile",  # free on Groq
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 3000,
                "temperature": 0.5
            },
            timeout=60
        )
        response.raise_for_status()
        return response.json()['choices'][0]['message']['content'].strip()
    except Exception as e:
        print(f"  Groq failed: {e}")
        return None

def _call_claude(prompt):
    if not ANTHROPIC_API_KEY:
        return None
    try:
        response = requests.post(
            ANTHROPIC_URL,
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json"
            },
            json={
                "model": "claude-haiku-4-5-20251001",  # cheapest / free-tier friendly
                "max_tokens": 3000,
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=90
        )
        response.raise_for_status()
        return response.json()['content'][0]['text'].strip()
    except Exception as e:
        print(f"  Claude failed: {e}")
        return None

def call_llm(prompt):
    """
    Tries providers in order: Gemini → Groq → Claude.
    Returns the first successful response, or None if all fail.
    """
    providers = [
        ("Gemini", _call_gemini),
        ("Groq",   _call_groq),
        ("Claude", _call_claude),
    ]
    for name, fn in providers:
        print(f"  → Trying {name}...")
        result = fn(prompt)
        if result:
            print(f"  ✅ {name} responded")
            return result
        print(f"  ❌ {name} unavailable, trying next...")
    print("  ❌ All LLM providers failed")
    return None

# ─────────────────────────────────────────────
#  NEWS FETCHING  (unchanged logic)
# ─────────────────────────────────────────────
def is_legal_relevant(title, summary=""):
    text = (title + " " + summary).lower()
    return any(kw in text for kw in LEGAL_KEYWORDS)

def fetch_news():
    articles = []
    published = load_published()
    for feed_url in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:10]:
                url = entry.get('link', '')
                title = entry.get('title', '')
                summary = entry.get('summary', '')[:500]
                if url in published:
                    continue
                if not is_legal_relevant(title, summary):
                    continue
                articles.append({
                    'title': title,
                    'url': url,
                    'summary': summary,
                    'source': feed.feed.get('title', 'Crypto News'),
                })
        except Exception as e:
            print(f"Error fetching {feed_url}: {e}")
    return articles, published

# ─────────────────────────────────────────────
#  ARTICLE + LINKEDIN GENERATION  (now uses call_llm)
# ─────────────────────────────────────────────
def generate_article(news_item):
    meta_prompt = f"""Based on this crypto legal news:
HEADLINE: {news_item['title']}
SUMMARY: {news_item['summary']}

Reply with exactly 3 lines, nothing else:
LINE1: [A compelling article title about the legal implications]
LINE2: [category - must be exactly one of: compliance, token, dao, startup, defi]
LINE3: [One sentence excerpt describing the article]"""

    meta_response = call_llm(meta_prompt)
    if not meta_response:
        return None

    lines = meta_response.strip().split('\n')
    title = news_item['title']
    category = 'compliance'
    excerpt = news_item['summary'][:150]

    for line in lines:
        line = line.strip()
        if line.startswith('LINE1:'):
            title = line.replace('LINE1:', '').strip().strip('"[]')
        elif line.startswith('LINE2:'):
            cat = line.replace('LINE2:', '').strip().lower().strip('"[]')
            if cat in ['compliance', 'token', 'dao', 'startup', 'defi']:
                category = cat
        elif line.startswith('LINE3:'):
            excerpt = line.replace('LINE3:', '').strip().strip('"[]')

    time.sleep(3)

    body_prompt = f"""You are Rahul Pareek, Founder of Web3Legals, Double Gold Medallist LLM from National Law University India.

Write a legal commentary article (800-1000 words) about this crypto legal development:
HEADLINE: {news_item['title']}
SOURCE: {news_item['source']}
SUMMARY: {news_item['summary']}

Cover:
1. What happened and legal significance
2. Implications for Web3 founders, DAOs, token projects
3. Practical action steps founders must take now
4. Relevant regulations (SEC, MiCA, SEBI, FATF, PMLA as relevant)
5. Conclusion with CTA to book free 30-min Legal Clarity Call at web3legals.com

Format with ## headings, **bold** key terms, bullet points.
Write the article directly — no title, no preamble, just the article body."""

    body_response = call_llm(body_prompt)
    if not body_response:
        return None

    return {
        'title': title,
        'category': category,
        'readtime': 8,
        'excerpt': excerpt,
        'body': body_response
    }

def generate_linkedin_draft(news_item, article_data):
    time.sleep(3)
    prompt = f"""You are Rahul Pareek, Founder of Web3Legals, Double Gold Medallist LLM from National Law University India.

A crypto legal article was just published on your blog:
ARTICLE TITLE: {article_data['title']}
ARTICLE EXCERPT: {article_data['excerpt']}
ORIGINAL NEWS: {news_item['title']}

Write a LinkedIn post (250-300 words) with this structure:

HOOK (1-2 lines): Shocking fact, bold statement or question. Never start with "I".
STORY/VALUE (3-5 short points): Key legal insights from the article.
CTA: "Full breakdown on my blog → web3legals.com" then ask a question to drive comments.
HASHTAGS: #Web3Legal #CryptoLaw #BlockchainLaw #Web3Legals + 3 more relevant ones.

Rules:
- Conversational tone — not corporate
- Max 3 emojis total
- Sound like a real person sharing genuine insight
- Mention web3legals.com in the CTA

Write ONLY the post. Nothing else."""

    post_text = call_llm(prompt)
    if not post_text:
        return None

    return {
        'id': f"draft-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
        'topic': article_data['title'],
        'category': article_data.get('category', 'compliance').capitalize(),
        'post': post_text,
        'word_count': len(post_text.split()),
        'source_url': news_item['url'],
        'source_title': news_item['title'],
        'generated_at': datetime.now(timezone.utc).isoformat(),
    }

# ─────────────────────────────────────────────
#  FILE SAVING  (unchanged)
# ─────────────────────────────────────────────
def save_linkedin_draft(draft):
    drafts_file = 'linkedin-drafts.json'
    try:
        with open(drafts_file, 'r') as f:
            data = json.load(f)
    except:
        data = {'drafts': []}
    data['drafts'].insert(0, draft)
    data['drafts'] = data['drafts'][:50]
    data['updated_at'] = datetime.now(timezone.utc).isoformat()
    with open(drafts_file, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"✅ LinkedIn draft saved!")

def save_article(article_data, news_url):
    title = article_data['title']
    slug = slugify(title)[:80]
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    excerpt = article_data['excerpt'].replace('"', "'")
    category = article_data['category']
    readtime = article_data.get('readtime', 8)
    body = article_data['body']

    markdown = f"""---
title: "{title}"
date: "{date}"
category: "{category}"
readtime: {readtime}
excerpt: "{excerpt}"
source_url: "{news_url}"
auto_generated: true
---

{body}

---

*Auto-generated by Web3Legals Global Crypto Legal Radar.*

*By Rahul Pareek — Founder, Web3Legals | LLM (International & Business Law), NLU*

*Disclaimer: For informational purposes only — not legal advice.*
"""
    filename = f"blog/{slug}.md"
    os.makedirs("blog", exist_ok=True)
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(markdown)
    print(f"✅ Article saved: {filename}")
    return slug

def update_blog_loader(new_slug):
    loader_path = "js/blog-loader.js"
    try:
        with open(loader_path, 'r') as f:
            content = f.read()
        if new_slug not in content:
            new_content = re.sub(
                r'(const CMS_ARTICLES = \[)',
                f'\\1\n  "{new_slug}",',
                content
            )
            with open(loader_path, 'w') as f:
                f.write(new_content)
            print(f"✅ blog-loader.js updated: {new_slug}")
    except Exception as e:
        print(f"Error updating blog-loader.js: {e}")

# ─────────────────────────────────────────────
#  PROCESS ONE ARTICLE  (shared by main + retry)
# ─────────────────────────────────────────────
def process_article(news_item, published):
    print(f"\n📝 Processing: {news_item['title']}")
    article_data = generate_article(news_item)
    if not article_data:
        print("⚠️  All LLMs failed — adding to retry queue")
        add_to_failed_queue(news_item)
        return False

    slug = save_article(article_data, news_item['url'])
    update_blog_loader(slug)

    print(f"📱 Generating LinkedIn draft...")
    linkedin_draft = generate_linkedin_draft(news_item, article_data)
    if linkedin_draft:
        save_linkedin_draft(linkedin_draft)
    else:
        print("⚠️  LinkedIn draft failed (article still published)")

    published.add(news_item['url'])
    save_published(published)
    print(f"🚀 Published: {article_data['title']}")
    return True

# ─────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────
def main():
    print("🔍 Web3Legals Crypto Legal Radar — Scanning...")

    if not any([GEMINI_API_KEY, GROQ_API_KEY, ANTHROPIC_API_KEY]):
        print("❌ No LLM API key found. Set at least one of: GEMINI_API_KEY, GROQ_API_KEY, ANTHROPIC_API_KEY")
        return

    available = []
    if GEMINI_API_KEY:    available.append("Gemini")
    if GROQ_API_KEY:      available.append("Groq")
    if ANTHROPIC_API_KEY: available.append("Claude")
    print(f"🔑 LLM providers available: {', '.join(available)}")

    published = load_published()

    # ── Step 1: retry any previously failed articles first ──
    failed_queue = load_failed_queue()
    if failed_queue:
        print(f"\n♻️  Retrying {len(failed_queue)} articles from previous failures...")
        for news_item in failed_queue[:]:
            if news_item['url'] in published:
                remove_from_failed_queue(news_item['url'])
                continue
            success = process_article(news_item, published)
            if success:
                remove_from_failed_queue(news_item['url'])
            time.sleep(10)

    # ── Step 2: fetch and process new articles ──
    articles, published = fetch_news()
    print(f"\n📰 Found {len(articles)} new relevant articles")

    if not articles:
        print("✅ No new developments found")
        return

    processed = 0
    for news_item in articles[:2]:
        success = process_article(news_item, published)
        if success:
            processed += 1
        if processed < 2:
            time.sleep(15)

    queue_size = len(load_failed_queue())
    print(f"\n✅ Done! Published {processed} articles + LinkedIn drafts.")
    if queue_size:
        print(f"📥 {queue_size} article(s) in retry queue — will process next run.")

if __name__ == "__main__":
    main()
