#!/usr/bin/env node
/**
 * Chiffre une page du dashboard avec une phrase de passe.
 *
 * Usage :
 *   CC_PASSPHRASE="..." node scripts/encrypt_page.js src/2026-07.html docs/index.html "July 2026"
 *
 * Sortie : un fichier HTML autonome qui demande la phrase de passe, dechiffre
 * le contenu dans le navigateur, puis affiche le dashboard.
 *
 * Chiffrement : PBKDF2-SHA256 (250 000 iterations) + AES-256-GCM.
 * Aucune dependance externe : crypto de Node cote generation, WebCrypto cote
 * navigateur. Le texte en clair ne quitte jamais la machine et n'est jamais
 * publie : seul le chiffre est ecrit dans docs/.
 */
const fs = require('fs');
const crypto = require('crypto');

const [inFile, outFile, label] = process.argv.slice(2);
const pass = process.env.CC_PASSPHRASE;

if (!inFile || !outFile) {
  console.error('Usage : CC_PASSPHRASE="..." node scripts/encrypt_page.js <entree.html> <sortie.html> [libelle]');
  process.exit(1);
}
if (!pass || pass.length < 8) {
  console.error('CC_PASSPHRASE absente ou trop courte (8 caracteres minimum).');
  process.exit(1);
}

const ITER = 250000;
const plain = fs.readFileSync(inFile);
const salt = crypto.randomBytes(16);
const iv = crypto.randomBytes(12);
const key = crypto.pbkdf2Sync(pass, salt, ITER, 32, 'sha256');
const cipher = crypto.createCipheriv('aes-256-gcm', key, iv);
const ct = Buffer.concat([cipher.update(plain), cipher.final()]);
const tag = cipher.getAuthTag();

const payload = {
  v: 1,
  iter: ITER,
  salt: salt.toString('base64'),
  iv: iv.toString('base64'),
  // WebCrypto attend le tag GCM concatene a la fin du chiffre
  ct: Buffer.concat([ct, tag]).toString('base64'),
};

const title = label ? `Jope · Customer Care · ${label}` : 'Jope · Customer Care';

const shell = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="robots" content="noindex, nofollow, noarchive, nosnippet">
<title>${title}</title>
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  body{background:#FAFAF7;color:#1C2B33;font-family:'Inter',system-ui,-apple-system,sans-serif;
       display:flex;align-items:center;justify-content:center;min-height:100vh;padding:24px}
  .box{background:#fff;border:1px solid #E4E6E1;border-radius:12px;padding:28px 30px;max-width:400px;width:100%}
  h1{font-size:19px;font-weight:600;margin-bottom:4px}
  p.sub{font-size:13px;color:#5A6B72;margin-bottom:18px}
  label{display:block;font-size:11.5px;font-weight:600;text-transform:uppercase;letter-spacing:0.05em;color:#5A6B72;margin-bottom:6px}
  input{width:100%;padding:10px 12px;font-size:15px;border:1px solid #E4E6E1;border-radius:8px;background:#FAFAF7;color:#1C2B33}
  input:focus{outline:none;border-color:#0F6E56;background:#fff}
  button{width:100%;margin-top:12px;padding:11px;font-size:14px;font-weight:600;color:#fff;background:#0F6E56;
         border:none;border-radius:8px;cursor:pointer}
  button:hover{background:#0B5744}
  button:disabled{background:#9AA7AC;cursor:default}
  .err{font-size:13px;color:#A32D2D;margin-top:10px;min-height:18px}
  .foot{font-size:11px;color:#9AA7AC;margin-top:16px;line-height:1.5}
  .wait{font-size:13px;color:#5A6B72}
  [hidden]{display:none!important}
</style>
</head>
<body>
<div class="box" id="box" hidden>
  <h1>Jope · Customer Care</h1>
  <p class="sub">${label ? label + ' · ' : ''}Internal report. Enter the team passphrase to open it.</p>
  <form id="f">
    <label for="p">Passphrase</label>
    <input id="p" type="password" autocomplete="current-password" autofocus>
    <button id="b" type="submit">Open the dashboard</button>
  </form>
  <div class="err" id="e"></div>
  <div class="foot">Contents are encrypted. Neither GitHub nor anyone without the passphrase can read this page.
  The passphrase is remembered for this browser tab only, so moving between months does not ask again;
  closing the tab forgets it.</div>
</div>
<div class="wait" id="wait">Opening...</div>
<script>
const DATA = ${JSON.stringify(payload)};
const b64 = s => Uint8Array.from(atob(s), c => c.charCodeAt(0));

// La phrase est gardee pour l onglet courant, sous une cle commune a toutes les
// pages du site : passer d un mois a l autre ne redemande donc rien. sessionStorage
// et non localStorage : l oubli au retrait de l onglet est voulu. Chaque page a son
// propre sel, donc on garde la phrase elle-meme et non la cle derivee.
const KEY = 'jope-cc-pass';
const box = document.getElementById('box');
const wait = document.getElementById('wait');

function remember(pass) { try { sessionStorage.setItem(KEY, pass); } catch (e) {} }
function forget() { try { sessionStorage.removeItem(KEY); } catch (e) {} }
function recall() { try { return sessionStorage.getItem(KEY); } catch (e) { return null; } }

function showForm(message) {
  wait.hidden = true;
  box.hidden = false;
  document.getElementById('e').textContent = message || '';
  const i = document.getElementById('p');
  i.value = '';
  i.focus();
}

async function unlock(pass) {
  if (!window.crypto || !crypto.subtle) {
    throw new Error('nocrypto');
  }
  const material = await crypto.subtle.importKey('raw', new TextEncoder().encode(pass), 'PBKDF2', false, ['deriveKey']);
  const key = await crypto.subtle.deriveKey(
    { name: 'PBKDF2', salt: b64(DATA.salt), iterations: DATA.iter, hash: 'SHA-256' },
    material, { name: 'AES-GCM', length: 256 }, false, ['decrypt']);
  const clear = await crypto.subtle.decrypt({ name: 'AES-GCM', iv: b64(DATA.iv) }, key, b64(DATA.ct));
  const html = new TextDecoder().decode(clear);
  remember(pass);
  document.open();
  document.write(html);
  document.close();
}

document.getElementById('f').addEventListener('submit', async ev => {
  ev.preventDefault();
  const err = document.getElementById('e');
  const btn = document.getElementById('b');
  const pass = document.getElementById('p').value;
  if (!pass) return;
  btn.disabled = true;
  btn.textContent = 'Opening...';
  err.textContent = '';
  try {
    await unlock(pass);
  } catch (e) {
    btn.disabled = false;
    btn.textContent = 'Open the dashboard';
    err.textContent = e && e.message === 'nocrypto'
      ? 'This browser blocks decryption on a local file. Open the published page over https.'
      : 'Wrong passphrase.';
  }
});

// Ouverture directe si l onglet a deja servi. Une phrase devenue invalide, par
// exemple apres un changement d equipe, est effacee et le formulaire revient.
(async () => {
  const saved = recall();
  if (!saved) { showForm(); return; }
  try {
    await unlock(saved);
  } catch (e) {
    forget();
    showForm(e && e.message === 'nocrypto'
      ? 'This browser blocks decryption on a local file. Open the published page over https.'
      : '');
  }
})();
</script>
</body>
</html>
`;

fs.writeFileSync(outFile, shell);
const kb = (fs.statSync(outFile).size / 1024).toFixed(1);
console.log(`OK ${inFile} -> ${outFile} (${kb} Ko chiffres, PBKDF2 ${ITER} iterations + AES-256-GCM)`);
