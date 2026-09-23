const API = 'http://localhost:5000/api';
let catalog = [];
let slide = 0;
const $ = (selector) => document.querySelector(selector);
const animeTitle = (anime) => anime?.title || anime?.title_english || 'Anime sin título';
const animeImage = (anime) => `${API}/media/${anime.mal_id || anime.movieId}/image`;

async function request(path) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15000);
  let response;
  try {
    response = await fetch(`${API}${path}`, { signal: controller.signal });
  } catch (error) {
    if (error.name === 'AbortError') throw new Error('La API tardó demasiado en responder');
    throw new Error('No se pudo conectar con el backend');
  } finally {
    clearTimeout(timeout);
  }
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.error || 'La API no respondió');
  return payload;
}

function toast(message) {
  const element = $('#toast');
  element.textContent = message;
  element.classList.add('show');
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => element.classList.remove('show'), 2800);
}

async function checkApi() {
  try {
    await request('/health');
    $('#apiStatus').textContent = 'API online';
    $('#apiStatusDot').classList.add('online');
  } catch (error) {
    $('#apiStatus').textContent = 'API offline';
    $('#apiStatusDot').classList.add('offline');
  }
}

function createCard(anime) {
  const element = document.createElement('article');
  element.className = 'card';
  const id = anime.mal_id || anime.movieId;
  element.innerHTML = `<span class="card-id">#${id || '--'}</span><img class="poster" src="${animeImage(anime)}" alt="Portada de ${animeTitle(anime)}" loading="lazy"><div class="card-body"><div class="card-title">${animeTitle(anime)}</div><div class="card-meta"><span>${anime.episodes ? `${anime.episodes} eps` : 'Serie'}</span><span class="score">★ ${anime.score || anime.predictedRating?.toFixed?.(1) || 'N/D'}</span></div></div>`;
  element.querySelector('.poster').addEventListener('error', (event) => {
    event.currentTarget.replaceWith(Object.assign(document.createElement('div'), { className: 'poster image-missing', textContent: 'Imagen no disponible' }));
  });
  element.addEventListener('click', () => showDetail(id));
  return element;
}

function renderCatalog(items) {
  const rail = $('#animeRail');
  rail.innerHTML = '';
  if (!items.length) {
    rail.innerHTML = '<div class="state">No hay títulos disponibles.</div>';
    $('#catalogStatus').textContent = 'Sin resultados';
    return;
  }
  items.forEach((anime) => rail.appendChild(createCard(anime)));
  catalog = items;
  $('#catalogStatus').textContent = `${items.length} títulos disponibles`;
  setHero(items[slide % items.length]);
}

async function loadCatalog(path = '/anime/top?limit=12') {
  $('#animeRail').innerHTML = '<div class="state">Consultando el catálogo...</div>';
  $('#catalogStatus').textContent = 'Consultando...';
  try {
    const payload = await request(path);
    renderCatalog(payload.data || []);
  } catch (error) {
    renderCatalog([]);
    $('#catalogStatus').textContent = error.message;
  }
}

async function searchAnime(query) {
  $('#animeRail').innerHTML = '<div class="state">Buscando anime...</div>';
  $('#catalogStatus').textContent = 'Buscando...';
  try {
    const payload = await request(`/anime/search?q=${encodeURIComponent(query)}&limit=12`);
    renderCatalog(payload.data || []);
  } catch (error) {
    toast(error.message);
  }
}

function setHero(anime) {
  if (!anime) return;
  $('#heroTitle').textContent = animeTitle(anime);
  $('#heroYear').textContent = anime.aired?.from?.slice?.(0, 4) || 'Destacado';
  $('#heroType').textContent = anime.type || 'Serie';
  $('#heroScore').textContent = `★ ${anime.score || '8.8'}`;
  $('#heroCopy').textContent = anime.synopsis || 'Una nueva historia para descubrir, con detalles, puntuaciones y episodios desde el catálogo de Anime Atlas.';
  $('#heroImage').style.backgroundImage = `url("${animeImage(anime)}")`;
  $('#heroDetail').onclick = () => showDetail(anime.mal_id);
  $('#watchButton').onclick = () => showDetail(anime.mal_id);
}

async function showDetail(id) {
  try {
    const payload = await request(`/anime/${id}`);
    setHero(payload.data || payload);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  } catch (error) {
    toast(error.message);
  }
}

$('#searchForm').addEventListener('submit', (event) => {
  event.preventDefault();
  const query = $('#searchInput').value.trim();
  query ? searchAnime(query) : loadCatalog();
});

document.querySelectorAll('[data-catalog]').forEach((button) => button.addEventListener('click', () => {
  document.querySelectorAll('[data-catalog]').forEach((item) => item.classList.remove('active'));
  button.classList.add('active');
  if (button.dataset.catalog === 'season') loadCatalog('/anime/season/now?limit=12');
  else if (button.dataset.catalog === 'search') {
    const query = $('#searchInput').value.trim();
    query ? searchAnime(query) : toast('Escribí un nombre para buscar.');
  } else loadCatalog();
}));

$('#nextSlide').onclick = () => { slide = (slide + 1) % catalog.length; setHero(catalog[slide]); };
$('#previousSlide').onclick = () => { slide = (slide - 1 + catalog.length) % catalog.length; setHero(catalog[slide]); };
$('#recommendForm').addEventListener('click', async () => {
  const resultList = $('#recommendationResults');
  resultList.innerHTML = '<span>Consultando el modelo...</span>';
  try {
    const limit = Number($('#recommendLimit').value);
    const result = await request(`/recommendations?limit=${limit}`);
    const recommendations = result.recommendations || [];
    resultList.innerHTML = recommendations.length
      ? `<div class="recommendation-summary">${result.returnedCount} de ${result.requestedLimit} recomendaciones disponibles</div>${recommendations.map((item) => `<div class="result-item"><strong>${item.title || `Anime #${item.movieId}`}</strong><small>#${item.movieId}</small><span>★ ${item.predictedRating.toFixed(2)}</span><a class="result-link" href="#" data-anime-id="${item.movieId}">Ver</a></div>`).join('')}`
      : `<span>${result.message || 'No hay recomendaciones para este usuario.'}</span>`;
    resultList.querySelectorAll('[data-anime-id]').forEach((link) => link.addEventListener('click', (clickEvent) => {
      clickEvent.preventDefault();
      showDetail(link.dataset.animeId);
    }));
  } catch (error) { toast(error.message); }
});

checkApi();
loadCatalog();
