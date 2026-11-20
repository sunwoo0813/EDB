import { readFile } from 'node:fs/promises';
import path from 'node:path';
import Screen from './Screen';
export default async function loadScreen(name) {
  const source = await readFile(path.join(process.cwd(), `${name}.html`), 'utf8');
  const body = source.match(/<body([^>]*)>([\s\S]*?)<\/body>/i);
  if (!body) throw new Error(`Missing body in ${name}.html`);
  const scripts = [...body[2].matchAll(/<script[^>]*>([\s\S]*?)<\/script>/gi)];
  return <Screen markup={body[2].replace(/<script[^>]*>[\s\S]*?<\/script>/gi, '')} script={scripts.map((match) => match[1]).join('\n')} bodyClass={body[1].match(/class="([^"]*)"/)?.[1] || ''} />;
}
