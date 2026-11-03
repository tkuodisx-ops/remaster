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

  // Supirkimo forma: atidaro el. pašto programą su užpildytu laišku
  var f = document.getElementById('supirkimo-forma');
  if (f) {
    f.addEventListener('submit', function (e) {
      e.preventDefault();
      var email = f.getAttribute('data-email');
      var pc = f.elements['pc'].value.trim();
      var kontaktas = f.elements['kontaktas'].value.trim();
      var body = 'Kompiuteris / specifikacijos:\n' + pc + '\n\nMano kontaktas:\n' + kontaktas;
      window.location.href = 'mailto:' + email +
        '?subject=' + encodeURIComponent('Kompiuterio supirkimo užklausa') +
        '&body=' + encodeURIComponent(body);
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
