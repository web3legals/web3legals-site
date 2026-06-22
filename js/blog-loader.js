// Web3Legals Blog Loader — auto-loads CMS articles with clean SEO URLs

const CMS_ARTICLES = [
  "india-s-crypto-legal-framework-in-2026-what-every-web3-founder-must-know",
  "orissa-high-court-s-crypto-ruling-what-it-means-for-indian-web3-founders",
  "oecd-crypto-reporting-framework-2027-how-indian-web3-businesses-must-prepare-now",
  "india-s-30-crypto-tax-1-tds-the-complete-legal-guide-for-web3-businesses",
  "mica-2-0-consultation-europe-s-legal-blueprint-for-stablecoins-and-defi",
  "whitebit-secures-mica-license-in-austria-ahead-of-july-1-eu-deadline"
];

const EMOJI_MAP = { compliance:"🛡", token:"🪙", dao:"🏛", startup:"🚀", defi:"🖼" };
const BADGE_MAP = { compliance:"badge-white", token:"badge-gold", dao:"badge-teal", startup:"badge-gold", defi:"badge-teal" };

async function fetchMeta(slug) {
  try {
    const res = await fetch(`/blog/${slug}.md`);
    if (!res.ok) return null;
    const raw = await res.text();
    const fm = { slug };
    if (raw.startsWith('---')) {
      const end = raw.indexOf('---', 3);
      if (end !== -1) {
        raw.slice(3, end).trim().split('\n').forEach(line => {
          const colon = line.indexOf(':');
          if (colon > -1) {
            const k = line.slice(0, colon).trim();
            const v = line.slice(colon + 1).trim().replace(/^["']|["']$/g, '');
            fm[k] = v;
          }
        });
      }
    }
    if (!fm.title || fm.title.trim() === '') return null;
    return fm;
  } catch(e) { return null; }
}

function makeCard(a) {
  const cat = a.category || 'compliance';
  // Use clean SEO URL — points to static HTML page built by GitHub Action
  const url = `/blog/${a.slug}`;
  const label = cat.charAt(0).toUpperCase() + cat.slice(1);
  const div = document.createElement('div');
  div.className = 'blog-card fade-up visible';
  div.dataset.category = cat;
  div.innerHTML = `
    <div class="blog-card-image">${EMOJI_MAP[cat] || '⚖'}</div>
    <div class="blog-card-body">
      <div class="blog-card-meta">
        <span class="badge ${BADGE_MAP[cat] || 'badge-white'}">${label}</span>
        <span>${a.readtime || '8'} min read</span>
      </div>
      <h3><a href="${url}">${a.title}</a></h3>
      <p>${a.excerpt || ''}</p>
      <a href="${url}" class="blog-read-more">Read article <span>→</span></a>
    </div>`;
  return div;
}

async function loadCMSArticles() {
  const mainGrid = document.getElementById('staticArticles');
  const placeholder = document.getElementById('cmsArticles');
  if (!mainGrid) return;
  if (placeholder) placeholder.remove();

  const articles = (await Promise.all(CMS_ARTICLES.map(fetchMeta))).filter(Boolean);
  if (articles.length === 0) return;

  articles.reverse().forEach(a => {
    const card = makeCard(a);
    mainGrid.insertBefore(card, mainGrid.firstChild);
  });

  document.querySelectorAll('.filter-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const cat = btn.dataset.filter;
      mainGrid.querySelectorAll('.blog-card').forEach(card => {
        card.style.display = (cat === 'all' || card.dataset.category === cat) ? '' : 'none';
      });
    });
  });
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', loadCMSArticles);
} else {
  loadCMSArticles();
}
