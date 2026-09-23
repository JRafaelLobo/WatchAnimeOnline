const API = 'http://localhost:5000/api';
const SESSION_KEY = 'animeAtlas.accessToken';
const $ = (selector) => document.querySelector(selector);
const session = { token: null, user: null, checking: true, version: 0 };
let catalog = [];
let slide = 0;
let authRequestId = 0;
let recommendationRequestId = 0;
let catalogRequestId = 0;
let detailRequestId = 0;
const animeTitle = (anime) => anime?.title || anime?.title_english || 'Anime sin título';
const animeId = (anime) => anime?.mal_id || anime?.movieId;
const animeImage = (anime) => `${API}/media/${encodeURIComponent(animeId(anime))}/image`;
const displayScore = (value, decimals = 1) => typeof value === 'number' && Number.isFinite(value) ? value.toFixed(decimals) : 'N/D';

class ApiError extends Error {
  constructor(message, status = 0) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

async function request(path, { method = 'GET', body, authenticated = false, timeoutMs = 15000 } = {}) {
  const headers = { Accept: 'application/json' };
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (authenticated) {
    if (!session.token) throw new ApiError('Iniciá sesión para continuar.', 401);
    headers.Authorization = `Bearer ${session.token}`;
  }
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(`${API}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
    });
    let payload;
    try {
      payload = await response.json();
    } catch (error) {
      if (error.name === 'AbortError') throw error;
      throw new ApiError('La API devolvió una respuesta que no se pudo leer.', response.status);
    }
    if (!response.ok) {
      const message = typeof payload?.error === 'string' ? payload.error : 'No se pudo completar la solicitud.';
      throw new ApiError(message, response.status);
    }
    return payload;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (error.name === 'AbortError') throw new ApiError('La API tardó demasiado en responder. Volvé a intentarlo.');
    throw new ApiError('No se pudo conectar con el backend. Revisá la conexión e intentá de nuevo.');
  } finally {
    clearTimeout(timeout);
  }
}

function node(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}

function toast(message) {
  const element = $('#toast');
  element.textContent = message;
  element.classList.add('show');
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => element.classList.remove('show'), 4000);
}

function saveToken(token) {
  session.token = token;
  try {
    if (token) sessionStorage.setItem(SESSION_KEY, token);
    else sessionStorage.removeItem(SESSION_KEY);
  } catch (_) {
    // Browsing still works when the browser disables session storage.
  }
}

function loginFeedback(message = '', isError = false) {
  const feedback = $('#loginFeedback');
  feedback.hidden = !message;
  feedback.classList.toggle('error', isError);
  feedback.setAttribute('role', isError ? 'alert' : 'status');
  feedback.setAttribute('aria-live', isError ? 'assertive' : 'polite');
  feedback.textContent = message;
  if (!message) {
    $('#loginEmail').removeAttribute('aria-invalid');
    $('#loginPassword').removeAttribute('aria-invalid');
  }
}

function resetPassword() {
  $('#loginPassword').value = '';
  $('#loginPassword').type = 'password';
  $('#togglePassword').textContent = 'Mostrar';
  $('#togglePassword').setAttribute('aria-label', 'Mostrar contraseña');
  $('#togglePassword').setAttribute('aria-pressed', 'false');
}

function setAuthBusy(busy, restoring = false) {
  $('#loginFields').disabled = busy;
  $('#loginForm').setAttribute('aria-busy', String(busy));
  $('#loginSubmit').textContent = busy ? (restoring ? 'Verificando sesión...' : 'Iniciando sesión...') : 'Entrar a mi cuenta →';
  $('#retrySession').disabled = busy;
}

function showView(view, focus = false) {
  const login = view === 'login';
  $('#loginView').hidden = !login;
  $('#catalogView').hidden = login;
  $('#searchForm').hidden = login;
  $('#openLogin').hidden = !!session.user || login;
  $('#sessionControls').hidden = login && !session.user;
  if (login && focus && !$('#loginFields').disabled) $('#loginEmail').focus();
  window.scrollTo({ top: 0, behavior: 'auto' });
}

function setRecommendationState(message) {
  $('#recommendationResults').replaceChildren(node('span', '', message));
  $('#recommendationResults').setAttribute('aria-busy', 'false');
  $('#recommendForm').disabled = session.checking;
  $('#recommendLimit').disabled = session.checking;
}

function addProfileDetail(label, value) {
  const row = node('div', 'profile-detail');
  row.append(node('dt', '', label), node('dd', '', value));
  $('#profileDetails').append(row);
}

function renderSession() {
  const user = session.user;
  const signedIn = !!user;
  $('#sessionName').hidden = !signedIn;
  $('#sessionName').textContent = signedIn ? user.nombre || user.profile?.username || user.email : '';
  $('#logoutButton').hidden = !signedIn;
  $('#openLogin').hidden = signedIn || !$('#loginView').hidden;
  $('#sessionControls').hidden = !signedIn && !$('#loginView').hidden;
  $('#profileLogin').hidden = signedIn;
  $('#profileDetails').hidden = !signedIn;
  $('#profileDetails').replaceChildren();
  $('#recommendationHeading').textContent = signedIn ? 'Recomendaciones para vos' : 'Recomendado por la comunidad';
  $('#recommendationDescription').textContent = signedIn
    ? 'Usamos el perfil asociado a tu cuenta y tus reseñas para encontrar tu próxima historia.'
    : 'Explorá recomendaciones generales o iniciá sesión para descubrir títulos según tu perfil.';
  $('#profileHeading').textContent = signedIn ? `Hola, ${user.nombre || user.profile?.username || 'de nuevo'}` : 'Descubrí algo para vos';
  $('#profileDescription').textContent = signedIn
    ? user.profile ? 'Tu perfil conectado a las recomendaciones.' : 'Tu cuenta todavía no tiene un perfil de recomendaciones asociado. Podés explorar las sugerencias de la comunidad.'
    : 'Ingresá con tu cuenta para usar tu perfil en las recomendaciones.';
  if (signedIn) {
    addProfileDetail('Correo', user.email || 'No disponible');
    if (user.profile) {
      addProfileDetail('Perfil', user.profile.username || 'Sin nombre');
      addProfileDetail('Reseñas', user.profile.reviewCount ?? 0);
      addProfileDetail('Puntuación media', displayScore(user.profile.meanScore, 2));
    }
    if (user.fechaCreacion) {
      const createdAt = new Date(user.fechaCreacion);
      if (!Number.isNaN(createdAt.getTime())) addProfileDetail('Miembro desde', createdAt.toLocaleDateString('es', { year: 'numeric', month: 'long' }));
    }
  }
  setRecommendationState(signedIn ? 'Generá una lista para descubrir recomendaciones según tu perfil.' : 'Generá una lista basada en los gustos de la comunidad.');
}

function setIdentity(token, user) {
  session.version += 1;
  recommendationRequestId += 1;
  session.checking = false;
  session.user = user;
  saveToken(token);
  resetPassword();
  $('#retrySession').hidden = true;
  renderSession();
}

function endSession(message, openLogin = true) {
  authRequestId += 1;
  clearTimeout(toast.timer);
  $('#toast').classList.remove('show');
  $('#toast').textContent = '';
  setIdentity(null, null);
  resetPassword();
  setAuthBusy(false);
  loginFeedback(message);
  showView(openLogin ? 'login' : 'catalog', openLogin);
}

async function restoreSession() {
  if (!session.token) {
    session.checking = false;
    renderSession();
    setAuthBusy(false);
    return;
  }
  const attempt = ++authRequestId;
  session.checking = true;
  $('#recommendForm').disabled = true;
  $('#recommendLimit').disabled = true;
  setAuthBusy(true, true);
  loginFeedback('Verificando tu sesión...');
  try {
    const result = await request('/auth/me', { authenticated: true });
    if (attempt !== authRequestId) return;
    if (!result?.id) throw new ApiError('La API no devolvió los datos de tu cuenta.');
    setIdentity(session.token, result);
    loginFeedback();
    showView('catalog');
    loadRecommendations();
  } catch (error) {
    if (attempt !== authRequestId) return;
    if (error.status === 401) {
      endSession('Tu sesión venció o dejó de ser válida. Iniciá sesión de nuevo.');
    } else {
      session.checking = false;
      renderSession();
      loginFeedback(`${error.message} No se pudo verificar tu sesión. Podés reintentar o explorar como invitado.`, true);
      $('#retrySession').hidden = false;
      showView('login');
    }
  } finally {
    if (attempt === authRequestId) setAuthBusy(false);
  }
}

async function signIn(event) {
  event.preventDefault();
  if ($('#loginFields').disabled) return;
  const email = $('#loginEmail').value.trim();
  const password = $('#loginPassword').value;
  const attempt = ++authRequestId;
  setAuthBusy(true);
  $('#retrySession').hidden = true;
  loginFeedback();
  try {
    const result = await request('/auth/login', { method: 'POST', body: { email, password } });
    if (attempt !== authRequestId) return;
    if (typeof result?.accessToken !== 'string' || !result.accessToken || !result?.user?.id) {
      throw new ApiError('La API no devolvió una sesión válida. Volvé a intentarlo.');
    }
    setIdentity(result.accessToken, result.user);
    resetPassword();
    showView('catalog');
    toast(`Bienvenido, ${result.user.nombre || result.user.profile?.username || 'de nuevo'}.`);
    loadRecommendations();
  } catch (error) {
    if (attempt !== authRequestId) return;
    const message = error.status === 401 ? 'El correo o la contraseña no son correctos. Revisá tus datos.' : error.message;
    loginFeedback(message, true);
    if (error.status === 401) {
      $('#loginEmail').setAttribute('aria-invalid', 'true');
      $('#loginPassword').setAttribute('aria-invalid', 'true');
    }
    resetPassword();
    if (session.token && !session.user) $('#retrySession').hidden = false;
  } finally {
    if (attempt === authRequestId) {
      setAuthBusy(false);
      if (!$('#loginView').hidden) $('#loginPassword').focus();
    }
  }
}

async function checkApi() {
  try {
    await request('/health');
    $('#apiStatus').textContent = 'API online';
    $('#apiStatusDot').classList.add('online');
  } catch (_) {
    $('#apiStatus').textContent = 'API offline';
    $('#apiStatusDot').classList.add('offline');
  }
}

function createCard(anime) {
  const element = node('article', 'card');
  const id = animeId(anime);
  element.tabIndex = 0;
  element.setAttribute('role', 'button');
  element.setAttribute('aria-label', `Ver detalle de ${animeTitle(anime)}`);
  const poster = node('img', 'poster');
  poster.src = animeImage(anime);
  poster.alt = `Portada de ${animeTitle(anime)}`;
  poster.loading = 'lazy';
  poster.addEventListener('error', () => {
    poster.replaceWith(node('div', 'poster image-missing', 'Imagen no disponible'));
  });
  const meta = node('div', 'card-meta');
  meta.append(node('span', '', anime.episodes ? `${anime.episodes} eps` : 'Serie'), node('span', 'score', `★ ${displayScore(anime.score ?? anime.predictedRating)}`));
  const body = node('div', 'card-body');
  body.append(node('div', 'card-title', animeTitle(anime)), meta);
  element.append(node('span', 'card-id', `#${id || '--'}`), poster, body);
  element.addEventListener('click', () => showDetail(id));
  element.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      showDetail(id);
    }
  });
  return element;
}

function renderCatalog(items) {
  const rail = $('#animeRail');
  rail.replaceChildren();
  catalog = Array.isArray(items) ? items : [];
  slide = 0;
  $('#previousSlide').disabled = catalog.length < 2;
  $('#nextSlide').disabled = catalog.length < 2;
  if (!catalog.length) {
    rail.append(node('div', 'state', 'No hay títulos disponibles.'));
    $('#catalogStatus').textContent = 'Sin resultados';
    return;
  }
  catalog.forEach((anime) => rail.append(createCard(anime)));
  $('#catalogStatus').textContent = `${catalog.length} títulos disponibles`;
  setHero(catalog[slide]);
}

async function loadCatalog(path = '/anime/top?limit=12') {
  const attempt = ++catalogRequestId;
  $('#animeRail').replaceChildren(node('div', 'state', 'Consultando el catálogo...'));
  $('#catalogStatus').textContent = 'Consultando...';
  try {
    const payload = await request(path);
    if (attempt !== catalogRequestId) return;
    renderCatalog(payload.data || []);
  } catch (error) {
    if (attempt !== catalogRequestId) return;
    renderCatalog([]);
    $('#catalogStatus').textContent = error.message;
  }
}

function searchAnime(query) {
  return loadCatalog(`/anime/search?q=${encodeURIComponent(query)}&limit=12`);
}

function setHero(anime) {
  if (!anime) return;
  $('#heroTitle').textContent = animeTitle(anime);
  $('#heroYear').textContent = anime.aired?.from?.slice?.(0, 4) || 'Destacado';
  $('#heroType').textContent = anime.type || 'Serie';
  $('#heroScore').textContent = `★ ${displayScore(anime.score)}`;
  $('#heroCopy').textContent = anime.synopsis || 'Una nueva historia para descubrir, con detalles, puntuaciones y episodios desde el catálogo de Anime Atlas.';
  $('#heroImage').style.backgroundImage = `url("${animeImage(anime)}")`;
  $('#heroDetail').disabled = !animeId(anime);
  $('#watchButton').disabled = !animeId(anime);
  $('#heroDetail').onclick = () => showDetail(animeId(anime));
  $('#watchButton').onclick = () => showDetail(animeId(anime));
}

async function showDetail(id) {
  if (!id) return;
  const attempt = ++detailRequestId;
  try {
    const payload = await request(`/anime/${encodeURIComponent(id)}`);
    if (attempt !== detailRequestId) return;
    setHero(payload.data || payload);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  } catch (error) {
    if (attempt === detailRequestId) toast(error.message);
  }
}

function renderRecommendations(result) {
  const list = $('#recommendationResults');
  list.replaceChildren();
  const recommendations = Array.isArray(result.recommendations) ? result.recommendations : [];
  if (result.mode) {
    list.append(node('div', 'recommendation-mode', result.mode === 'personalized' ? 'Según tu perfil' : 'Selección de la comunidad'));
  }
  if (result.message) list.append(node('p', 'recommendation-note', result.message));
  if (!recommendations.length) {
    if (!result.message) list.append(node('span', '', 'No hay recomendaciones disponibles por ahora.'));
    return;
  }
  list.append(node('div', 'recommendation-summary', `${result.returnedCount ?? recommendations.length} de ${result.requestedLimit ?? $('#recommendLimit').value} recomendaciones disponibles`));
  recommendations.forEach((item) => {
    const row = node('div', 'result-item');
    const button = node('button', 'result-link', 'Ver');
    button.type = 'button';
    button.setAttribute('aria-label', `Ver detalle de ${item.title || `Anime #${item.movieId}`}`);
    button.addEventListener('click', () => showDetail(item.movieId));
    row.append(node('strong', '', item.title || `Anime #${item.movieId}`), node('small', '', `#${item.movieId}`), node('span', 'result-score', `★ ${displayScore(item.predictedRating, 2)}`), button);
    list.append(row);
  });
}

async function loadRecommendations() {
  if (session.checking) return;
  const attempt = ++recommendationRequestId;
  const version = session.version;
  const personalized = !!session.user;
  const isCurrent = () => attempt === recommendationRequestId && version === session.version;
  const resultList = $('#recommendationResults');
  resultList.replaceChildren(node('span', '', personalized
    ? 'Buscando recomendaciones para vos... La primera generación puede tardar un momento.'
    : 'Consultando recomendaciones de la comunidad... La primera generación puede tardar un momento.'));
  resultList.setAttribute('aria-busy', 'true');
  $('#recommendForm').disabled = true;
  $('#recommendLimit').disabled = true;
  try {
    const limit = Number($('#recommendLimit').value);
    const path = personalized ? '/recommendations/me' : '/recommendations';
    const result = await request(`${path}?limit=${limit}`, { authenticated: personalized, timeoutMs: 120000 });
    if (!isCurrent()) return;
    renderRecommendations(result);
  } catch (error) {
    if (!isCurrent()) return;
    if (personalized && error.status === 401) {
      endSession('Tu sesión venció. Iniciá sesión de nuevo para ver tus recomendaciones.');
    } else {
      resultList.replaceChildren(node('span', 'result-error', error.message));
    }
  } finally {
    if (isCurrent()) {
      resultList.setAttribute('aria-busy', 'false');
      $('#recommendForm').disabled = false;
      $('#recommendLimit').disabled = false;
    }
  }
}

function activateTab(name) {
  document.querySelectorAll('[data-catalog]').forEach((button) => {
    const active = button.dataset.catalog === name;
    button.classList.toggle('active', active);
    button.setAttribute('aria-pressed', String(active));
  });
}

$('#searchForm').addEventListener('submit', (event) => {
  event.preventDefault();
  const query = $('#searchInput').value.trim();
  activateTab(query ? 'search' : 'top');
  query ? searchAnime(query) : loadCatalog();
});

document.querySelectorAll('[data-catalog]').forEach((button) => button.addEventListener('click', () => {
  activateTab(button.dataset.catalog);
  if (button.dataset.catalog === 'season') loadCatalog('/anime/season/now?limit=12');
  else if (button.dataset.catalog === 'search') {
    const query = $('#searchInput').value.trim();
    query ? searchAnime(query) : toast('Escribí un nombre para buscar.');
  } else loadCatalog();
}));

$('#nextSlide').onclick = () => {
  if (!catalog.length) return;
  slide = (slide + 1) % catalog.length;
  setHero(catalog[slide]);
};
$('#previousSlide').onclick = () => {
  if (!catalog.length) return;
  slide = (slide - 1 + catalog.length) % catalog.length;
  setHero(catalog[slide]);
};
$('#recommendForm').addEventListener('click', loadRecommendations);
$('#loginForm').addEventListener('submit', signIn);
['#loginEmail', '#loginPassword'].forEach((selector) => $(selector).addEventListener('input', () => {
  if ($('#loginEmail').hasAttribute('aria-invalid') || $('#loginPassword').hasAttribute('aria-invalid')) loginFeedback();
}));
$('#openLogin').addEventListener('click', () => { loginFeedback(); showView('login', true); });
$('#profileLogin').addEventListener('click', () => { loginFeedback(); showView('login', true); });
$('#continueGuest').addEventListener('click', () => endSession('', false));
$('#logoutButton').addEventListener('click', () => endSession('Cerraste sesión. Podés volver a ingresar cuando quieras.'));
$('#retrySession').addEventListener('click', restoreSession);
$('#togglePassword').addEventListener('click', () => {
  const visible = $('#loginPassword').type === 'password';
  $('#loginPassword').type = visible ? 'text' : 'password';
  $('#togglePassword').textContent = visible ? 'Ocultar' : 'Mostrar';
  $('#togglePassword').setAttribute('aria-label', visible ? 'Ocultar contraseña' : 'Mostrar contraseña');
  $('#togglePassword').setAttribute('aria-pressed', String(visible));
});

try {
  session.token = sessionStorage.getItem(SESSION_KEY);
} catch (_) {
  session.token = null;
}
checkApi();
loadCatalog();
restoreSession();
