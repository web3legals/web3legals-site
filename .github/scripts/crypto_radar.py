#!/usr/bin/env python3
import os
import re
import json
import time
import requests
import feedparser
from datetime import datetime, timezone
from slugify import slugify

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"

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

PUBLISHED_FILE = ".github/scripts/published_urls.json"

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
            continue
    return articles, published

def call_gemini(prompt, retries=3):
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
            result = response.json()
            return result['candidates'][0]['content']['parts'][0]['text'].strip()
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response else 0
            if status in [429, 503] and attempt < retries - 1:
                wait = 30 * (attempt + 1)
                print(f"Gemini busy ({status}) — waiting {wait}s then retrying... (attempt {attempt+1}/{retries})")
                time.sleep(wait)
                continue
            print(f"Gemini API error: {e}")
            return None
        except Exception as e:
            if attempt < retries - 1:
                print(f"Error (attempt {attempt+1}/{retries}): {e} — retrying in 15s...")
                time.sleep(15)
                continue
            print(f"Gemini API error: {e}")
            return None
    return None

def generate_article(news_item):
    meta_prompt = f"""Based on this crypto legal news:
HEADLINE: {news_item['title']}
SUMMARY: {news_item['summary']}

Reply with exactly 3 lines, nothing else:
LINE1: [A compelling article title about the legal implications]
LINE2: [category - must be exactly one of: compliance, token, dao, startup, defi]
LINE3: [One sentence excerpt describing the article]"""

    meta_response = call_gemini(meta_prompt)
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

    time.sleep(5)

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

    body_response = call_gemini(body_prompt)
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
    time.sleep(5)
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

    post_text = call_gemini(prompt)
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
        print(f"Error: {e}")

def main():
    print("🔍 Web3Legals Crypto Legal Radar — Scanning...")
    if not GEMINI_API_KEY:
        print("❌ GEMINI_API_KEY not set")
        return

    articles, published = fetch_news()
    print(f"📰 Found {len(articles)} new relevant articles")

    if not articles:
        print("✅ No new developments found")
        return

    processed = 0
    for news_item in articles[:2]:
        print(f"\n📝 Processing: {news_item['title']}")
        article_data = generate_article(news_item)
        if not article_data:
            print("⚠️ Skipping — could not generate article")
            continue
        slug = save_article(article_data, news_item['url'])
        update_blog_loader(slug)
        print(f"📱 Generating LinkedIn draft...")
        linkedin_draft = generate_linkedin_draft(news_item, article_data)
        if linkedin_draft:
            save_linkedin_draft(linkedin_draft)
        published.add(news_item['url'])
        save_published(published)
        processed += 1
        print(f"🚀 Published: {article_data['title']}")
        if processed < 2:
            time.sleep(15)

    print(f"\n✅ Done! Published {processed} articles + LinkedIn drafts.")

if __name__ == "__main__":
    main()
