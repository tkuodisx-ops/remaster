// Mobilus meniu
(function () {
  var b = document.getElementById('burger');
  var m = document.getElementById('menu');
  if (b && m) {
    b.addEventListener('click', function () { m.classList.toggle('open'); });
    m.addEventListener('click', function (e) {
      if (e.target.tagName === 'A') m.classList.remove('open');
    });
  }

  // Supirkimo forma: siunčia užklausą (jei nustatytas adresas), kitaip atidaro el. paštą
  var f = document.getElementById('supirkimo-forma');
  if (f) {
    f.addEventListener('submit', function (e) {
      e.preventDefault();
      var pc = f.elements['pc'].value.trim();
      var kontaktas = f.elements['kontaktas'].value.trim();
      var endpoint = f.getAttribute('data-endpoint');
      var note = document.getElementById('form-note');
      if (endpoint) {
        var btn = f.querySelector('button[type=submit]');
        btn.disabled = true;
        var body = new URLSearchParams({
          irenginys: pc, kontaktas: kontaktas, website: f.elements['website'].value
        });
        fetch(endpoint, { method: 'POST', mode: 'no-cors', body: body }).then(function () {
          f.reset(); btn.disabled = false;
          if (note) { note.textContent = 'Ačiū! Užklausą gavome, netrukus susisieksime.'; note.style.color = '#4ade80'; }
        }).catch(function () {
          btn.disabled = false;
          if (note) { note.textContent = 'Nepavyko išsiųsti. Parašykite mums el. paštu.'; note.style.color = '#f87171'; }
        });
        return;
      }
      var email = f.getAttribute('data-email');
      var text = 'Kompiuteris / specifikacijos:\n' + pc + '\n\nMano kontaktas:\n' + kontaktas;
      window.location.href = 'mailto:' + email +
        '?subject=' + encodeURIComponent('Kompiuterio supirkimo užklausa') +
        '&body=' + encodeURIComponent(text);
    });
  }
})();

// Straipsnių filtravimas pagal kategoriją
(function () {
  var chips = document.getElementById('chips');
  var grid = document.getElementById('art-grid');
  if (!chips || !grid) return;
  chips.addEventListener('click', function (e) {
    var b = e.target.closest('.chip');
    if (!b) return;
    var cat = b.getAttribute('data-cat');
    chips.querySelectorAll('.chip').forEach(function (c) { c.classList.toggle('on', c === b); });
    grid.querySelectorAll('.art-card').forEach(function (card) {
      card.classList.toggle('hide', !!cat && card.getAttribute('data-cat') !== cat);
    });
  });
})();
