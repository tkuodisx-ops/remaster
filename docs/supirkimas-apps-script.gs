// Remaster.lt – supirkimo užklausų priėmimas (Google Apps Script)
// 1) Atidarykite Google lentelę -> Extensions (Plėtiniai) -> Apps Script
// 2) Įklijuokite šį kodą, pakeiskite KEY į savo slaptą žodį
// 3) Deploy -> New deployment -> Web app: Execute as "Me", Who has access "Anyone" -> Deploy
// 4) Nukopijuokite Web app URL į admino Nustatymus, o KEY įveskite skiltyje "Supirkimas"

var KEY = 'PAKEISK_SAVO_SLAPTAZODI';
var SHEET = 'Supirkimas';

function sheet_() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sh = ss.getSheetByName(SHEET);
  if (!sh) {
    sh = ss.insertSheet(SHEET);
    sh.appendRow(['ID', 'Laikas', 'Įranga', 'Kontaktas', 'Būsena']);
  }
  return sh;
}
function out_(o) {
  return ContentService.createTextOutput(JSON.stringify(o)).setMimeType(ContentService.MimeType.JSON);
}

// Užklausa iš svetainės formos
function doPost(e) {
  var p = (e && e.parameter) || {};
  if (p.website) return out_({ ok: true });            // spam spąstai
  var irang = String(p.irenginys || '').trim().slice(0, 1500);
  var kont = String(p.kontaktas || '').trim().slice(0, 200);
  if (!irang || !kont) return out_({ ok: false, error: 'tuscia' });
  var id = String(new Date().getTime());
  var laikas = Utilities.formatDate(new Date(), 'Europe/Vilnius', 'yyyy-MM-dd HH:mm');
  sheet_().appendRow([id, laikas, irang, kont, 'Naujas']);
  try {
    MailApp.sendEmail(Session.getEffectiveUser().getEmail(), 'Nauja supirkimo užklausa',
      'Įranga:\n' + irang + '\n\nKontaktas: ' + kont);
  } catch (err) { }
  return out_({ ok: true });
}

// Admino skydelis: sąrašas, būsena, trynimas (reikia KEY)
function doGet(e) {
  var p = (e && e.parameter) || {};
  if (p.key !== KEY) return out_({ ok: false, error: 'key' });
  var sh = sheet_();
  var rows = sh.getDataRange().getValues();
  if (p.action === 'delete' || p.action === 'status') {
    for (var i = 1; i < rows.length; i++) {
      if (String(rows[i][0]) === String(p.id)) {
        if (p.action === 'delete') sh.deleteRow(i + 1);
        else sh.getRange(i + 1, 5).setValue(p.value === 'Perziureta' ? 'Peržiūrėta' : 'Naujas');
        return out_({ ok: true });
      }
    }
    return out_({ ok: false, error: 'nerasta' });
  }
  var items = [];
  for (var j = 1; j < rows.length; j++) {
    items.push({ id: String(rows[j][0]), laikas: String(rows[j][1]), irenginys: rows[j][2], kontaktas: rows[j][3], busena: rows[j][4] });
  }
  items.reverse();
  return out_({ ok: true, items: items });
}
