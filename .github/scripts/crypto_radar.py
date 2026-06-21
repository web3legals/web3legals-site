#!/usr/bin/env python3
"""
Web3Legals — Global Crypto Legal Radar
Monitors RSS feeds for crypto legal news, generates articles using Google Gemini (free),
and publishes them automatically to web3legals.com
"""

import os
import re
import json
import time
import requests
import feedparser
from datetime import datetime, timezone
from slugify import slugify

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"

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

def generate_article(news_item):
    prompt = f"""You are Rahul Pareek, Founder of Web3Legals and a Double Gold Medallist in LLM (International & Business Law) from National Law University, India. You are a senior crypto-asset regulatory strategist.

A major crypto legal development has just been reported:

HEADLINE: {news_item['title']}
SOURCE: {news_item['source']}
SUMMARY: {news_item['summary']}
URL: {news_item['url']}

Write a comprehensive legal commentary article (800-1200 words) about this development for Web3 founders and crypto businesses.

The article must:
1. Start with a compelling introduction explaining what happened
2. Explain the legal significance in plain English
3. Cover implications for Web3 founders, DAOs, token projects, and crypto businesses
4. Include practical action steps founders must take
5. Reference relevant regulations (SEC, MiCA, SEBI, FATF, PMLA as relevant)
6. End with a conclusion and CTA to book a free legal clarity call at Web3Legals

Format in Markdown with ## headings, **bold** key terms, bullet points for lists.
Category must be one of: compliance, token, dao, startup, defi

IMPORTANT: Respond ONLY with valid JSON, no markdown code blocks:
{{"title": "Article title", "category": "compliance", "readtime": 8, "excerpt": "One sentence summary", "body": "Full markdown article"}}"""

    try:
        response = requests.post(
            f"{GEMINI_URL}?key={GEMINI_API_KEY}",
            headers={"Content-Type": "application/json"},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.7, "maxOutputTokens": 4000}
            },
            timeout=60
        )
        response.raise_for_status()
        result = response.json()
        text = result['candidates'][0]['content']['parts'][0]['text'].strip()
        text = re.sub(r'^```[a-z]*\n?', '', text)
        text = re.sub(r'\n?```$', '', text).strip()
        return json.loads(text)
    except Exception as e:
        print(f"Error generating article: {e}")
        return None

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

*This article was automatically generated by Web3Legals Global Crypto Legal Radar.*

*By Rahul Pareek — Founder, Web3Legals | LLM (International & Business Law), NLU*

*Disclaimer: For informational purposes only — not legal advice.*
"""

    filename = f"blog/{slug}.md"
    os.makedirs("blog", exist_ok=True)
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(markdown)
    print(f"✅ Saved: {filename}")
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
            continue
        slug = save_article(article_data, news_item['url'])
        update_blog_loader(slug)
        published.add(news_item['url'])
        save_published(published)
        processed += 1
        print(f"🚀 Published: {article_data['title']}")
        if processed < 2:
            time.sleep(3)

    print(f"\n✅ Done! Published {processed} articles.")

if __name__ == "__main__":
    main()
