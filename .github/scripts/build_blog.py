#!/usr/bin/env python3
"""
Web3Legals — Static Blog Builder
Converts all .md files in /blog into proper SEO-optimized HTML pages
Runs on every GitHub push via GitHub Actions
"""

import os
import re
import json
import glob
from datetime import datetime

# ── HTML TEMPLATE ─────────────────────────────────────────────────────────────

def get_template(title, excerpt, category, date, readtime, slug, body_html, toc_html=""):
    badge_map = {
        'compliance': 'badge-white',
        'token': 'badge-gold',
        'dao': 'badge-teal',
        'startup': 'badge-gold',
        'defi': 'badge-teal'
    }
    badge = badge_map.get(category, 'badge-white')
    cat_label = category.capitalize() if category else 'Article'

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} — Web3Legals</title>
<meta name="description" content="{excerpt}">
<meta property="og:title" content="{title} — Web3Legals">
<meta property="og:description" content="{excerpt}">
<meta property="og:type" content="article">
<meta property="og:url" content="https://web3legals.com/blog/{slug}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{title}">
<meta name="twitter:description" content="{excerpt}">
<link rel="canonical" href="https://web3legals.com/blog/{slug}">
<script type="application/ld+json">
{{
  "@context": "https://schema.org",
  "@type": "Article",
  "headline": "{title}",
  "description": "{excerpt}",
  "author": {{
    "@type": "Person",
    "name": "Rahul Pareek",
    "url": "https://web3legals.com/about"
  }},
  "publisher": {{
    "@type": "Organization",
    "name": "Web3Legals",
    "url": "https://web3legals.com"
  }},
  "datePublished": "{date}",
  "url": "https://web3legals.com/blog/{slug}"
}}
</script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/css/style.css">
<style>
.article-body {{ max-width: 740px; margin: 0 auto; }}
.article-body h2 {{ font-size: 1.5rem; margin: 44px 0 14px; color: var(--white); padding-top: 8px; border-top: 1px solid var(--border2); }}
.article-body h3 {{ font-size: 1.15rem; margin: 28px 0 10px; color: var(--gold); }}
.article-body p {{ font-size: 1.05rem; color: var(--gray); line-height: 1.85; margin-bottom: 18px; }}
.article-body ul, .article-body ol {{ padding-left: 24px; margin-bottom: 18px; }}
.article-body li {{ font-size: 1rem; color: var(--gray); line-height: 1.8; margin-bottom: 8px; }}
.article-body strong {{ color: var(--white); font-weight: 600; }}
.article-body em {{ font-style: italic; }}
.article-body hr {{ border: none; border-top: 1px solid var(--border2); margin: 36px 0; }}
.article-body blockquote {{ background: rgba(201,168,76,0.07); border-left: 3px solid var(--gold); padding: 16px 20px; margin: 28px 0; }}
.article-body blockquote p {{ margin: 0; font-size: 0.95rem; color: #E2C97E; }}
.article-body a {{ color: var(--gold); }}
.article-meta {{ display: flex; align-items: center; gap: 20px; flex-wrap: wrap; margin-bottom: 40px; padding-bottom: 32px; border-bottom: 1px solid var(--border2); }}
.article-meta span {{ font-size: 0.85rem; color: var(--gray); }}
.toc {{ background: var(--glass); border: 1px solid var(--border2); border-radius: var(--radius-lg); padding: 24px 28px; margin-bottom: 44px; }}
.toc h4 {{ font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.08em; color: var(--gold); margin-bottom: 14px; }}
.toc ul {{ list-style: none; padding: 0; margin: 0; }}
.toc li {{ font-size: 0.875rem; color: var(--gray); padding: 5px 0; border-bottom: 1px solid var(--border2); }}
.toc li:last-child {{ border: none; }}
.toc a {{ color: var(--gray); text-decoration: none; }}
.toc a:hover {{ color: var(--gold); }}
.article-cta {{ background: linear-gradient(135deg, rgba(201,168,76,0.06), rgba(29,158,117,0.04)); border: 1px solid var(--border); border-radius: var(--radius-lg); padding: 48px 36px; text-align: center; margin-top: 64px; }}
</style>
</head>
<body>
<nav class="nav" id="nav">
  <div class="nav-inner">
    <a href="/index.html" class="nav-logo"><div class="nav-logo-icon">W3</div><span>Web3<span class="text-gold">Legals</span></span></a>
    <ul class="nav-links">
      <li><a href="/index.html">Home</a></li>
      <li><a href="/services.html">Services</a></li>
      <li><a href="/about.html">About</a></li>
      <li><a href="/blog.html" class="active">Blog</a></li>
      <li><a href="/contact.html">Contact</a></li>
    </ul>
    <div class="nav-cta"><a href="/contact.html" class="btn btn-gold">Book a Call</a></div>
    <div class="nav-hamburger" id="hamburger"><span></span><span></span><span></span></div>
  </div>
</nav>
<div class="mobile-menu" id="mobileMenu">
  <a href="/index.html">Home</a><a href="/services.html">Services</a>
  <a href="/about.html">About</a><a href="/blog.html">Blog</a><a href="/contact.html">Contact</a>
  <a href="/contact.html" class="btn btn-gold" style="margin-top:16px">Book a Free Call</a>
</div>

<section style="padding: 140px 0 80px;">
  <div class="container">
    <div class="article-body">
      <a href="/blog.html" style="font-size:0.85rem;color:var(--gold);display:inline-flex;align-items:center;gap:6px;margin-bottom:24px;text-decoration:none">← Back to Blog</a>
      <div class="badge {badge}" style="margin-bottom:20px">{cat_label}</div>
      <h1 style="font-size:clamp(1.8rem,4vw,2.6rem);margin-bottom:20px">{title}</h1>
      <div class="article-meta">
        <span>By <a href="/about.html" style="color:var(--gold);text-decoration:none">Rahul Pareek</a></span>
        <span>·</span>
        <span>{date}</span>
        <span>·</span>
        <span>{readtime} min read</span>
      </div>
      {toc_html}
      <div>{body_html}</div>
      <div class="article-cta">
        <div class="eyebrow">Get Expert Advice</div>
        <h2 style="font-size:1.6rem;margin-bottom:12px">Need legal clarity?</h2>
        <p style="max-width:480px;margin:0 auto 28px">Book a free 30-minute Legal Clarity Call with Rahul Pareek, Founder of Web3Legals — no obligation.</p>
        <a href="/contact.html" class="btn btn-gold">Book a Free Call →</a>
      </div>
    </div>
  </div>
</section>

<footer class="footer">
  <div class="container">
    <div class="footer-grid">
      <div class="footer-brand">
        <a href="/index.html" class="nav-logo" style="display:inline-flex"><div class="nav-logo-icon">W3</div><span>Web3<span class="text-gold">Legals</span></span></a>
        <p>Legal clarity for the decentralized world.</p>
        <div class="footer-social">
          <a href="https://linkedin.com/in/rahulpareek2302" class="social-link">in</a>
          <a href="#" class="social-link">𝕏</a>
        </div>
      </div>
      <div class="footer-col"><h4>Services</h4><ul class="footer-links"><li><a href="/services.html">Token Advisory</a></li><li><a href="/services.html">DAO Wrappers</a></li><li><a href="/services.html">KYC/AML</a></li></ul></div>
      <div class="footer-col"><h4>Company</h4><ul class="footer-links"><li><a href="/about.html">About Rahul</a></li><li><a href="/blog.html">Blog</a></li><li><a href="/contact.html">Contact</a></li></ul></div>
      <div class="footer-col"><h4>Contact</h4><ul class="footer-links"><li><a href="mailto:rahul@web3legals.com">rahul@web3legals.com</a></li><li><a href="/contact.html">Book a Call</a></li></ul></div>
    </div>
    <div class="footer-bottom">
      <span>© 2026 Web3Legals. Founded by <a href="/about.html">Rahul Pareek</a>.</span>
      <span>Disclaimer: Informational only — not legal advice.</span>
    </div>
  </div>
</footer>
<button class="back-top" id="backTop" aria-label="Back to top">↑</button>
<script src="/js/main.js"></script>
</body>
</html>'''

# ── MARKDOWN PARSER ───────────────────────────────────────────────────────────

def parse_frontmatter(content):
    """Extract frontmatter and body from markdown file."""
    fm = {}
    body = content
    if content.startswith('---'):
        end = content.find('---', 3)
        if end != -1:
            fm_text = content[3:end].strip()
            for line in fm_text.split('\n'):
                colon = line.find(':')
                if colon > -1:
                    key = line[:colon].strip()
                    val = line[colon+1:].strip().strip('"\'')
                    fm[key] = val
            body = content[end+3:].strip()
    return fm, body

def markdown_to_html(md):
    """Convert markdown to HTML."""
    html = md

    # Headings
    html = re.sub(r'^#### (.+)$', r'<h4>\1</h4>', html, flags=re.MULTILINE)
    html = re.sub(r'^### (.+)$', r'<h3>\1</h3>', html, flags=re.MULTILINE)
    html = re.sub(r'^## (.+)$', r'<h2>\1</h2>', html, flags=re.MULTILINE)
    html = re.sub(r'^# (.+)$', r'<h1>\1</h1>', html, flags=re.MULTILINE)

    # Bold and italic
    html = re.sub(r'\*\*\*(.+?)\*\*\*', r'<strong><em>\1</em></strong>', html)
    html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html)
    html = re.sub(r'\*(.+?)\*', r'<em>\1</em>', html)

    # Links
    html = re.sub(r'\[([^\]]+)\]\(([^\)]+)\)', r'<a href="\2">\1</a>', html)

    # Horizontal rules
    html = re.sub(r'^---+$', '<hr>', html, flags=re.MULTILINE)

    # Blockquotes
    html = re.sub(r'^> (.+)$', r'<blockquote><p>\1</p></blockquote>', html, flags=re.MULTILINE)

    # Process lists
    lines = html.split('\n')
    result = []
    in_ul = False
    in_ol = False

    for line in lines:
        if re.match(r'^- (.+)$', line):
            if not in_ul:
                result.append('<ul>')
                in_ul = True
            result.append(re.sub(r'^- (.+)$', r'<li>\1</li>', line))
        elif re.match(r'^\d+\. (.+)$', line):
            if not in_ol:
                result.append('<ol>')
                in_ol = True
            result.append(re.sub(r'^\d+\. (.+)$', r'<li>\1</li>', line))
        else:
            if in_ul:
                result.append('</ul>')
                in_ul = False
            if in_ol:
                result.append('</ol>')
                in_ol = False
            result.append(line)

    if in_ul:
        result.append('</ul>')
    if in_ol:
        result.append('</ol>')

    html = '\n'.join(result)

    # Paragraphs — wrap non-tag lines
    paragraphs = []
    for block in html.split('\n\n'):
        block = block.strip()
        if not block:
            continue
        if block.startswith('<'):
            paragraphs.append(block)
        else:
            paragraphs.append(f'<p>{block}</p>')

    return '\n'.join(paragraphs)

def build_toc(body_html):
    """Build table of contents from h2 headings."""
    h2s = re.findall(r'<h2>(.+?)</h2>', body_html)
    if len(h2s) < 2:
        return ""

    # Add IDs to h2s
    toc_items = []
    for i, heading in enumerate(h2s):
        slug = re.sub(r'[^a-z0-9]+', '-', heading.lower()).strip('-')
        toc_items.append(f'<li><a href="#{slug}">{heading}</a></li>')

    toc_html = f'''<div class="toc">
<h4>Table of Contents</h4>
<ul>{"".join(toc_items)}</ul>
</div>'''

    # Add IDs to h2 tags in body
    def add_id(match):
        heading = match.group(1)
        slug = re.sub(r'[^a-z0-9]+', '-', heading.lower()).strip('-')
        return f'<h2 id="{slug}">{heading}</h2>'

    return toc_html

def add_h2_ids(body_html):
    """Add ID attributes to h2 headings for TOC links."""
    def replacer(match):
        heading = match.group(1)
        slug = re.sub(r'[^a-z0-9]+', '-', heading.lower()).strip('-')
        return f'<h2 id="{slug}">{heading}</h2>'
    return re.sub(r'<h2>(.+?)</h2>', replacer, body_html)

# ── SITEMAP BUILDER ───────────────────────────────────────────────────────────

def build_sitemap(slugs):
    """Generate sitemap.xml for Google indexing."""
    static_pages = [
        'https://web3legals.com/',
        'https://web3legals.com/services.html',
        'https://web3legals.com/about.html',
        'https://web3legals.com/blog.html',
        'https://web3legals.com/contact.html',
    ]

    urls = static_pages + [f'https://web3legals.com/blog/{slug}' for slug in slugs]

    sitemap = '<?xml version="1.0" encoding="UTF-8"?>\n'
    sitemap += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for url in urls:
        sitemap += f'  <url><loc>{url}</loc></url>\n'
    sitemap += '</urlset>'

    with open('sitemap.xml', 'w') as f:
        f.write(sitemap)
    print(f"✅ sitemap.xml generated with {len(urls)} URLs")

# ── ROBOTS.TXT ────────────────────────────────────────────────────────────────

def build_robots():
    robots = """User-agent: *
Allow: /

Sitemap: https://web3legals.com/sitemap.xml
"""
    with open('robots.txt', 'w') as f:
        f.write(robots)
    print("✅ robots.txt generated")

# ── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    print("🔨 Web3Legals Static Blog Builder — Starting...")

    md_files = glob.glob('blog/*.md')
    print(f"📄 Found {len(md_files)} markdown files")

    slugs = []
    built = 0

    for md_path in md_files:
        try:
            with open(md_path, 'r', encoding='utf-8') as f:
                content = f.read()

            fm, body_md = parse_frontmatter(content)

            if not fm.get('title'):
                print(f"⚠️ Skipping {md_path} — no title")
                continue

            slug = os.path.basename(md_path).replace('.md', '')
            title = fm.get('title', 'Article')
            excerpt = fm.get('excerpt', '')[:160]
            category = fm.get('category', 'compliance')
            date = fm.get('date', '2026')
            readtime = fm.get('readtime', '8')

            # Convert markdown to HTML
            body_html = markdown_to_html(body_md)
            body_html = add_h2_ids(body_html)
            toc_html = build_toc(body_html)

            # Generate full HTML page
            html = get_template(
                title=title,
                excerpt=excerpt,
                category=category,
                date=date,
                readtime=readtime,
                slug=slug,
                body_html=body_html,
                toc_html=toc_html
            )

            # Save as HTML file in blog/ folder
            out_path = f'blog/{slug}.html'
            with open(out_path, 'w', encoding='utf-8') as f:
                f.write(html)

            slugs.append(slug)
            built += 1
            print(f"✅ Built: {out_path}")

        except Exception as e:
            print(f"❌ Error processing {md_path}: {e}")
            continue

    # Generate sitemap and robots.txt
    build_sitemap(slugs)
    build_robots()

    print(f"\n✅ Done! Built {built} HTML pages.")
    print(f"🗺️  Sitemap: https://web3legals.com/sitemap.xml")

if __name__ == "__main__":
    main()
