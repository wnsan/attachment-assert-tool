// Demo app for the e2e examples: / -> e2e/site/index.html, /files/<name> -> examples/<name> (as attachment)
const http = require('http');
const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const port = Number(process.env.PORT || 4321);

http.createServer((req, res) => {
  const url = decodeURIComponent(new URL(req.url, 'http://x').pathname);
  if (url.startsWith('/files/')) {
    const file = path.join(root, 'examples', path.basename(url));
    if (!fs.existsSync(file)) { res.writeHead(404); return res.end(); }
    res.writeHead(200, { 'Content-Type': 'application/pdf', 'Content-Disposition': `attachment; filename="${path.basename(file)}"` });
    return fs.createReadStream(file).pipe(res);
  }
  res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
  fs.createReadStream(path.join(root, 'e2e', 'site', 'index.html')).pipe(res);
}).listen(port, () => console.log(`demo app on http://127.0.0.1:${port}`));
