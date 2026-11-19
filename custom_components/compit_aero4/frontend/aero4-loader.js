const version = new URL(import.meta.url).searchParams.get('v');

async function loadCards() {
  while (!customElements.get('home-assistant') || !document.querySelector('home-assistant')?.shadowRoot) {
    await new Promise(resolve => setTimeout(resolve, 50));
  }

  await Promise.all(['aero4-card.js', 'aero4-schedule-card.js'].map(name => {
    const url = new URL(name, import.meta.url);
    if (version) url.searchParams.set('v', version);
    return import(url.href);
  }));
}

void loadCards().catch(error => console.error('AERO C14: could not load dashboard cards.', error));
