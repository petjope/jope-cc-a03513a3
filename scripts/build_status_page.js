#!/usr/bin/env node
/*
 * Genere la page de repli publiee quand la generation du dashboard a echoue.
 *
 * Raison d etre : le 4 septembre 2026 le run mensuel s est arrete sans rien
 * publier et sans rien dire. Regle posee par Jeremy le meme jour : une page
 * part dans tous les cas, et elle nomme ce qui a manque.
 *
 * Usage : node scripts/build_status_page.js <month YYYY-MM> <label> <sortie.html> [log]
 */
const fs = require('fs');

const [month, label, out, logPath] = process.argv.slice(2);
if (!month || !label || !out) {
  console.error('usage: build_status_page.js <YYYY-MM> <"Month YYYY"> <out.html> [run.log]');
  process.exit(1);
}

const esc = (s) => String(s).replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));

let tail = '';
try {
  if (logPath && fs.existsSync(logPath)) {
    const lines = fs.readFileSync(logPath, 'utf8').split(/\r?\n/);
    tail = lines.slice(-40).join('\n');
  }
} catch (e) {
  tail = '(log illisible: ' + e.message + ')';
}

const stamp = new Date().toISOString().replace('T', ' ').slice(0, 16) + ' UTC';

fs.writeFileSync(out, `<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Jope CC Dashboard - ${esc(label)}</title>
<style>
 :root{--ink:#14181d;--ink-2:#4a545e;--ink-3:#7b8794;--line:#e3e7eb;--amber:#b45309;--amber-bg:#fef6e7}
 body{margin:0;background:#f7f8f9;color:var(--ink);font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
 .wrap{max-width:760px;margin:0 auto;padding:48px 22px 64px}
 h1{font-size:23px;margin:0 0 4px;letter-spacing:-.01em}
 .sub{color:var(--ink-3);font-size:13px;margin-bottom:28px}
 .alert{background:var(--amber-bg);border:1px solid #f0d9a8;border-left:3px solid var(--amber);
        border-radius:7px;padding:16px 18px;margin-bottom:24px}
 .alert b{color:var(--amber)}
 .card{background:#fff;border:1px solid var(--line);border-radius:9px;padding:18px 20px;margin-bottom:16px}
 h2{font-size:14px;margin:0 0 10px;text-transform:uppercase;letter-spacing:.06em;color:var(--ink-3)}
 p{margin:0 0 10px}
 ol{margin:0;padding-left:20px}li{margin-bottom:6px}
 pre{background:#f2f4f6;border:1px solid var(--line);border-radius:6px;padding:12px;
     font:11.5px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;overflow-x:auto;white-space:pre-wrap;color:var(--ink-2)}
 .foot{color:var(--ink-3);font-size:12px;margin-top:26px;border-top:1px solid var(--line);padding-top:14px}
</style></head><body><div class="wrap">
<h1>Customer Care dashboard, ${esc(label)}</h1>
<div class="sub">Automated run, ${esc(stamp)}</div>

<div class="alert">
  <b>This month's dashboard could not be generated.</b>
  <p style="margin-top:8px;margin-bottom:0">The scheduled run started but did not produce a page. No figure below
  has been estimated or carried over from a previous month. The run retries on its own tomorrow at 9:00.</p>
</div>

<div class="card">
  <h2>What to do</h2>
  <ol>
    <li>Open Claude Code in the dashboard project and run <code>/cc-monthly</code> to generate ${esc(month)} by hand.</li>
    <li>Or wait for the retry tomorrow at 9:00, which runs automatically.</li>
    <li>The log tail below names the step that stopped.</li>
  </ol>
</div>

<div class="card">
  <h2>Run log, last lines</h2>
  <pre>${esc(tail || '(no log available)')}</pre>
</div>

<div class="foot">Previous months stay available in the navigation bar of the last published dashboard.
This placeholder is replaced as soon as a run succeeds.</div>
</div></body></html>
`);
console.log('status page written: ' + out);
