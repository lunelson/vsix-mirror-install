import cfonts from 'cfonts';

export function renderBanner(): void {
  const result = cfonts.render('vsix-bridge', {
    font: 'tiny',
    colors: ['candy'],
    space: false,
  });
  if (result) {
    console.log(result.string);
  }
}

export function renderInfo(pkg: { name: string; version: string; description?: string }): void {
  const info = `│  ${pkg.name} v${pkg.version}`;
  const desc = pkg.description ? ` — ${pkg.description}` : '';
  console.log(`${info}${desc}\n`);
}
