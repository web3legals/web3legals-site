// Web3Legals Blog Loader — auto-discovers and displays CMS articles
// Add new slugs to CMS_ARTICLES when you publish via admin panel

const CMS_ARTICLES = [
  "india-s-crypto-legal-framework-in-2026-what-every-web3-founder-must-know",
  "orissa-high-court-s-crypto-ruling-what-it-means-for-indian-web3-founders",
  "oecd-crypto-reporting-framework-2027-how-indian-web3-businesses-must-prepare-now",
  "india-s-30-crypto-tax-1-tds-the-complete-legal-guide-for-web3-businesses"
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
    return fm;
  } catch(e) { return null; }
}

function makeCard(a) {
  const cat = a.category || 'compliance';
  const url = `/blog-post.html?post=${a.slug}`;
  const label = cat.charAt(0).toUpperCase() + cat.slice(1);
  const div = document.createElement('div');
  div.className = 'blog-card fade-up';
  div.dataset.category = cat;
  div.innerHTML = `
    <div class="blog-card-image">${EMOJI_MAP[cat] || '⚖'}</div>
    <div class="blog-card-body">
      <div class="blog-card-meta">
        <span class="badge ${BADGE_MAP[cat] || 'badge-white'}">${label}</span>
        <span>${a.readtime || '8'} min read</span>
      </div>
      <h3><a href="${url}">${a.title || 'Article'}</a></h3>
      <p>${a.excerpt || ''}</p>
      <a href="${url}" class="blog-read-more">Read article <span>→</span></a>
    </div>`;
  return div;
}

async function loadCMSArticles() {
  const container = document.getElementById('cmsArticles');
  if (!container) return;

  const articles = (await Promise.all(CMS_ARTICLES.map(fetchMeta))).filter(Boolean);

  if (articles.length === 0) {
    container.innerHTML = '';
    return;
  }

  // Build grid
  const grid = document.createElement('div');
  grid.className = 'grid-3';
  grid.style.marginBottom = '0';

  articles.forEach(a => {
    const card = makeCard(a);
    grid.appendChild(card);
    setTimeout(() => {
      new IntersectionObserver(([e]) => {
        if (e.isIntersecting) { e.target.classList.add('visible'); }
      }, { threshold: 0.1 }).observe(card);
    }, 100);
  });

  container.innerHTML = '';
  container.appendChild(grid);

  // Hook into filter buttons
  document.querySelectorAll('.filter-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const cat = btn.dataset.filter;
      container.querySelectorAll('.blog-card').forEach(card => {
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
