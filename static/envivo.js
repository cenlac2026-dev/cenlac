// CENLAC en vivo: pregunta cada pocos segundos si otro usuario guardó un cambio.
// Si lo hay, avisa quién fue y actualiza la pantalla (salvo que se esté escribiendo algo: ahí ofrece un botón).
(function () {
  var cuerpo = document.body;
  var ultimo = parseInt(cuerpo.getAttribute('data-ultima-novedad') || '0', 10);
  if (!cuerpo.hasAttribute('data-ultima-novedad')) return;
  var CADA = 6000, CADA_OCULTA = 45000, timer = null, editando = false, pendiente = false;
  var indicador = document.getElementById('envivo');
  var etiquetaConectados = document.getElementById('envivo-conectados');
  var panel = document.getElementById('envivo-panel');

  // Si el usuario empezó a escribir en un formulario, no se recarga la pantalla sola.
  document.addEventListener('input', function (e) { if (e.target.closest('form:not(.filtros)')) editando = true; });
  document.addEventListener('submit', function () { editando = false; });

  function seguroRecargar() {
    if (editando) return false;
    var a = document.activeElement;
    if (a && /^(INPUT|TEXTAREA|SELECT)$/.test(a.tagName) && a.type !== 'button' && a.type !== 'submit') return false;
    if (document.querySelector('.w-lista details[open], dialog[open], .envivo-panel:not([hidden])')) return false;
    return true;
  }

  var caja = document.createElement('div');
  caja.className = 'envivo-avisos';
  caja.setAttribute('aria-live', 'polite');
  document.body.appendChild(caja);

  function avisar(n, conBoton) {
    var d = document.createElement('div');
    d.className = 'envivo-aviso';
    var partes = n.texto.split(' ');
    var ic = document.createElement('b'); ic.textContent = partes[0] + ' ';
    var t = document.createElement('span'); t.textContent = n.quien + ' ' + partes.slice(1).join(' ');
    d.appendChild(ic); d.appendChild(t);
    if (conBoton) {
      var b = document.createElement('button');
      b.type = 'button'; b.textContent = 'Actualizar';
      b.addEventListener('click', function () { location.reload(); });
      d.appendChild(b);
    }
    caja.appendChild(d);
    setTimeout(function () { d.classList.add('sale'); setTimeout(function () { d.remove(); }, 400); }, conBoton ? 20000 : 6000);
  }

  function mostrarConectados(lista) {
    if (!etiquetaConectados) return;
    etiquetaConectados.textContent = lista.length > 1 ? ' · ' + lista.length + ' conectados' : '';
    if (indicador) indicador.title = 'Conectados ahora: ' + (lista.join(', ') || '-') + '. Tocar para ver los últimos cambios.';
  }

  function preguntar() {
    clearTimeout(timer);
    fetch('/novedades?desde=' + ultimo, {credentials: 'same-origin', headers: {'Accept': 'application/json'}})
      .then(function (r) { if (r.redirected || !r.ok) throw new Error('sin sesión'); return r.json(); })
      .then(function (d) {
        if (indicador) indicador.classList.remove('sin-conexion');
        mostrarConectados(d.conectados || []);
        var ajenas = (d.novedades || []).filter(function (n) { return !n.mio; }).reverse();
        if (d.ultimo > ultimo) {
          ultimo = d.ultimo;
          if (ajenas.length) {
            var recargar = seguroRecargar();
            ajenas.slice(-3).forEach(function (n) { avisar(n, !recargar); });
            if (recargar) {
              try { sessionStorage.setItem('cenlac-scroll', String(window.scrollY)); } catch (e) {}
              setTimeout(function () { if (seguroRecargar()) location.reload(); }, 1800);
            } else pendiente = true;
          }
        }
      })
      .catch(function () { if (indicador) indicador.classList.add('sin-conexion'); })
      .then(function () { timer = setTimeout(preguntar, document.hidden ? CADA_OCULTA : CADA); });
  }

  // Al volver a la pantalla después de una actualización automática, se mantiene la posición.
  try {
    var y = sessionStorage.getItem('cenlac-scroll');
    if (y !== null) { sessionStorage.removeItem('cenlac-scroll'); window.scrollTo(0, parseInt(y, 10)); }
  } catch (e) {}

  document.addEventListener('visibilitychange', function () { if (!document.hidden) preguntar(); });

  // Panel de últimos cambios
  if (indicador && panel) {
    indicador.addEventListener('click', function (e) {
      e.preventDefault();
      if (!panel.hidden) { panel.hidden = true; return; }
      fetch('/novedades', {credentials: 'same-origin'}).then(function (r) { return r.json(); }).then(function (d) {
        var ul = panel.querySelector('ul'); ul.innerHTML = '';
        if (!d.novedades.length) { var li0 = document.createElement('li'); li0.textContent = 'Todavía no hay cambios registrados.'; ul.appendChild(li0); }
        d.novedades.forEach(function (n) {
          var li = document.createElement('li');
          var el = document.createElement(n.enlace ? 'a' : 'span');
          if (n.enlace) el.href = n.enlace;
          var q = document.createElement('b'); q.textContent = n.mio ? 'Vos' : n.quien;
          el.appendChild(document.createTextNode(n.texto.split(' ')[0] + ' '));
          el.appendChild(q);
          el.appendChild(document.createTextNode(' ' + n.texto.split(' ').slice(1).join(' ')));
          var h = document.createElement('small'); h.textContent = n.hace;
          li.appendChild(el); li.appendChild(h); ul.appendChild(li);
        });
        panel.querySelector('.envivo-conectados-lista').textContent = 'Conectados ahora: ' + (d.conectados.join(', ') || '-');
        panel.hidden = false;
      });
    });
    document.addEventListener('click', function (e) { if (!panel.hidden && !e.target.closest('#envivo-panel, #envivo')) panel.hidden = true; });
  }

  timer = setTimeout(preguntar, 1500);
})();
