/* Authentication is kept in an HttpOnly cookie issued by the API. */
window.AnimeAuth = (() => {
  const API = 'http://localhost:5000/api';
  const $ = (selector) => document.querySelector(selector);
  const pendingRequests = new Set();
  const channel = typeof BroadcastChannel === 'function' ? new BroadcastChannel('anime-session') : null;
  let user = null;
  let mode = 'login';
  let busy = false;
  let sessionVersion = 0;
  let expiryTimer;
  let onAuthenticated;

  function message(text = '', state = 'error') {
    const element = $('#authMessage');
    element.textContent = text;
    element.dataset.state = state;
    element.hidden = !text;
  }

  function setBusy(value, label) {
    busy = value;
    $('#authFields').disabled = value;
    $('#loginTab').disabled = value;
    $('#registerTab').disabled = value;
    $('#authSwitch').disabled = value;
    $('#authForm').setAttribute('aria-busy', String(value));
    $('#authSubmitLabel').textContent = label || (mode === 'register' ? 'Crear mi cuenta' : 'Ingresar');
  }

  function setMode(nextMode, focus = true) {
    mode = nextMode;
    const registering = mode === 'register';
    $('#nameField').hidden = !registering;
    $('#confirmField').hidden = !registering;
    $('#authName').disabled = !registering;
    $('#authName').required = registering;
    $('#authConfirmPassword').disabled = !registering;
    $('#authConfirmPassword').required = registering;
    $('#passwordHint').hidden = !registering;
    $('#authPassword').minLength = registering ? 8 : 1;
    $('#authPassword').maxLength = registering ? 128 : 1024;
    $('#authPassword').autocomplete = registering ? 'new-password' : 'current-password';
    $('#authPassword').value = '';
    $('#authConfirmPassword').value = '';
    $('#authConfirmPassword').setCustomValidity('');
    $('#authPassword').type = 'password';
    $('#togglePassword').setAttribute('aria-pressed', 'false');
    $('#togglePassword').setAttribute('aria-label', 'Mostrar contraseña');
    $('#loginTab').setAttribute('aria-pressed', String(!registering));
    $('#registerTab').setAttribute('aria-pressed', String(registering));
    $('#authTitle').textContent = registering ? 'Empezá tu nueva historia.' : 'Qué bueno verte de nuevo.';
    $('#authSubtitle').textContent = registering
      ? 'Creá tu cuenta y descubrí qué anime ver después.'
      : 'Ingresá a tu cuenta. Tu próximo anime te espera.';
    $('#authSwitchPrompt').textContent = registering ? '¿Ya tenés una cuenta?' : '¿Primera vez por aquí?';
    $('#authSwitch').textContent = registering ? 'Ingresar' : 'Crear una cuenta';
    setBusy(false);
    message();
    if (focus) $(registering ? '#authName' : '#authEmail').focus();
  }

  function invalidateRequests() {
    sessionVersion += 1;
    pendingRequests.forEach((controller) => controller.abort());
    pendingRequests.clear();
    clearTimeout(expiryTimer);
  }

  function showLogin(text = '', state = 'error') {
    invalidateRequests();
    user = null;
    $('#appPage').hidden = true;
    $('#appPage').inert = true;
    $('#authView').hidden = false;
    $('#authView').inert = false;
    document.title = 'Ingresar | WatchAnimeOnline';
    setMode('login', false);
    message(text, state);
    document.dispatchEvent(new Event('anime:logout'));
    if (text) $('#authEmail').focus();
  }

  function scheduleExpiry(expiresAt) {
    clearTimeout(expiryTimer);
    if (!Number.isFinite(expiresAt)) return;
    expiryTimer = setTimeout(() => {
      showLogin('Tu sesión expiró. Ingresá de nuevo para continuar.');
    }, Math.max(0, expiresAt * 1000 - Date.now()));
  }

  function enterApplication(profile, expiresAt) {
    invalidateRequests();
    user = profile;
    $('#authForm').reset();
    $('#authView').hidden = true;
    $('#authView').inert = true;
    $('#appPage').hidden = false;
    $('#appPage').inert = false;
    $('#userName').textContent = profile.nombre;
    $('#userName').title = profile.nombre;
    $('#userAvatar').textContent = profile.nombre.trim().charAt(0).toLocaleUpperCase('es');
    document.title = 'WatchAnimeOnline | Descubrí tu próximo anime';
    scheduleExpiry(expiresAt);
    onAuthenticated();
    $('#searchInput').focus({ preventScroll: true });
    window.scrollTo({ top: 0 });
  }

  async function request(path, { authenticated = true, ...options } = {}) {
    if (authenticated && !user) {
      throw Object.assign(new Error('Ingresá para continuar.'), { silent: true });
    }
    const version = sessionVersion;
    const controller = new AbortController();
    pendingRequests.add(controller);
    let timedOut = false;
    const timeout = setTimeout(() => { timedOut = true; controller.abort(); }, 15000);
    const headers = new Headers(options.headers);
    headers.set('Accept', 'application/json');
    const method = (options.method || 'GET').toUpperCase();
    if (options.body && typeof options.body === 'object') {
      headers.set('Content-Type', 'application/json');
      options.body = JSON.stringify(options.body);
    }
    if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) {
      const csrf = document.cookie.split('; ').find((cookie) => cookie.startsWith('csrf_access_token='));
      if (csrf) headers.set('X-CSRF-TOKEN', decodeURIComponent(csrf.slice('csrf_access_token='.length)));
    }
    try {
      const response = await fetch(`${API}${path}`, {
        ...options, headers, method, credentials: 'include', cache: 'no-store', signal: controller.signal,
      });
      const payload = await response.json().catch(() => ({}));
      if (version !== sessionVersion) throw Object.assign(new Error('La sesión cambió.'), { silent: true });
      if (!response.ok) {
        const error = Object.assign(new Error(payload.error || payload.msg || 'No se pudo completar la solicitud.'), { status: response.status });
        if (response.status === 401 && authenticated) {
          showLogin('Tu sesión expiró. Ingresá de nuevo para continuar.');
          error.silent = true;
        }
        throw error;
      }
      return payload;
    } catch (error) {
      if (error.name === 'AbortError') {
        throw Object.assign(new Error(timedOut ? 'El servidor tardó demasiado. Intentá de nuevo.' : 'Solicitud cancelada.'), { silent: !timedOut });
      }
      if (error instanceof TypeError) throw new Error('No se pudo conectar con el servidor. Intentá de nuevo en unos momentos.');
      throw error;
    } finally {
      clearTimeout(timeout);
      pendingRequests.delete(controller);
    }
  }

  async function restoreSession() {
    setBusy(true, 'Comprobando sesión…');
    try {
      const profile = await request('/auth/me', { authenticated: false });
      enterApplication(profile, profile.expiresAt);
    } catch (error) {
      if (!error.silent) showLogin([401, 404, 422].includes(error.status) ? '' : error.message);
    } finally {
      setBusy(false);
    }
  }

  $('#loginTab').addEventListener('click', () => setMode('login'));
  $('#registerTab').addEventListener('click', () => setMode('register'));
  $('#authSwitch').addEventListener('click', () => setMode(mode === 'login' ? 'register' : 'login'));
  $('#togglePassword').addEventListener('click', () => {
    const visible = $('#authPassword').type === 'password';
    $('#authPassword').type = visible ? 'text' : 'password';
    $('#togglePassword').setAttribute('aria-pressed', String(visible));
    $('#togglePassword').setAttribute('aria-label', visible ? 'Ocultar contraseña' : 'Mostrar contraseña');
  });
  for (const selector of ['#authPassword', '#authConfirmPassword']) {
    $(selector).addEventListener('input', () => $('#authConfirmPassword').setCustomValidity(''));
  }
  $('#authName').addEventListener('input', () => $('#authName').setCustomValidity(''));

  $('#authForm').addEventListener('submit', async (event) => {
    event.preventDefault();
    if (busy) return;
    message();
    const registering = mode === 'register';
    if (registering && !$('#authName').value.trim()) {
      $('#authName').setCustomValidity('Escribí tu nombre.');
    }
    if (registering && $('#authPassword').value !== $('#authConfirmPassword').value) {
      $('#authConfirmPassword').setCustomValidity('Las contraseñas no coinciden.');
    }
    if (!$('#authForm').reportValidity()) return;
    const body = { email: $('#authEmail').value.trim(), password: $('#authPassword').value };
    if (registering) body.nombre = $('#authName').value.trim();
    setBusy(true, registering ? 'Creando tu cuenta…' : 'Ingresando…');
    try {
      const result = await request(registering ? '/auth/register' : '/auth/login', {
        authenticated: false, method: 'POST', body,
      });
      enterApplication(result.user, result.expiresAt);
      channel?.postMessage('signed-in');
    } catch (error) {
      if (!error.silent) message(error.message);
    } finally {
      setBusy(false);
    }
  });

  $('#logoutButton').addEventListener('click', async () => {
    const button = $('#logoutButton');
    button.disabled = true;
    try {
      await request('/auth/logout', { authenticated: false, method: 'POST' });
      showLogin('Cerraste tu sesión. ¡Hasta el próximo episodio!', 'success');
      channel?.postMessage('signed-out');
    } catch (error) {
      if (!error.silent) document.dispatchEvent(new CustomEvent('anime:message', { detail: error.message }));
    } finally {
      button.disabled = false;
    }
  });

  if (channel) channel.onmessage = ({ data }) => {
    if (data === 'signed-out' && user) showLogin('Tu sesión se cerró en otra pestaña.', 'success');
    if (data === 'signed-in' && !user && !busy) restoreSession();
  };

  document.addEventListener('visibilitychange', async () => {
    if (document.visibilityState !== 'visible' || !user) return;
    try {
      const profile = await request('/auth/me');
      scheduleExpiry(profile.expiresAt);
    } catch (error) {
      if (error.status === 404) showLogin('Ingresá de nuevo para continuar.');
    }
  });

  return {
    API,
    request,
    start(callback) {
      onAuthenticated = callback;
      setMode('login', false);
      restoreSession();
    },
  };
})();
