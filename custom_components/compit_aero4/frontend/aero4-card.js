                                                                              
const KEYS = ['outdoor_temperature','supply_temperature','extract_temperature','exhaust_temperature',
  'room_temperature','room_temperature_setpoint','fan_a_percent','fan_b_percent',
  'supply_fan_speed','extract_fan_speed','ventilation_requested','ventilation_mode_requested',
  'parameter_boost_duration','operating_mode','manual_speed','ventilation_command_status','bypass_mode',
  'parameter_ventilation_enabled','parameter_gwc_mode','parameter_fireplace_active',
  'parameter_holiday_mode','parameter_away_mode','parameter_scan_progress',
  'bypass_requested','bypass_reported_open','bypass_control','bypass_command_status',
  'boost_control','boost_command_status','boost_requested','boost_active','aero_online',
  'filter_days_remaining','filter_reset','parameter_filter_reminder_period',
  'air_co2','air_pm25_percent','air_pm10_percent','parameter_sensor_co2_start'];
const DEMO = {outdoor_temperature:'8.4',supply_temperature:'19.8',extract_temperature:'22.1',
  exhaust_temperature:'11.6',room_temperature:'22.1',room_temperature_setpoint:'22.5',
  fan_a_percent:'35',fan_b_percent:'35',ventilation_requested:'B2',ventilation_mode_requested:'schedule',
  operating_mode:'schedule',manual_speed:'unavailable',parameter_ventilation_enabled:'on',
  parameter_gwc_mode:'auto',parameter_fireplace_active:'off',parameter_holiday_mode:'off',parameter_away_mode:'off',
  parameter_boost_duration:'0',bypass_mode:'OFF',bypass_requested:'OFF',bypass_reported_open:'off',boost_control:'off',boost_requested:'off',boost_active:'off',aero_online:'on',filter_days_remaining:'24',parameter_filter_reminder_period:'90'};
const fan = `<svg viewBox="0 0 40 40" aria-hidden="true"><circle cx="20" cy="20" r="18" fill="none" stroke="currentColor" opacity=".25"/><g class="rotor"><path fill="currentColor" d="M19 18C3 13 11 1 18 7c4 3 4 7 2 11m3 1c5-16 17-8 11-1-3 4-7 4-11 2m-2 3c16 5 8 17 1 11-4-3-4-7-2-11m-3-2C13 37 1 29 7 22c3-4 7-4 11-2"/><circle cx="20" cy="20" r="4" fill="currentColor"/></g></svg>`;
const EN={'Od\u015bwie\u017canie':'Refreshing','Ostatni odczyt':'Last reading',
  'Czerpnia u góry po lewej, nawiew na dole po prawej. Wywiew u góry po prawej, wyrzutnia na dole po lewej. Dwa oddzielne kanały wymiany ciepła.':'Outdoor intake at top left, supply at bottom right. Extract at top right, exhaust at bottom left. Two separate air channels.',
  'C14 · REKUPERACJA':'C14 · HEAT RECOVERY','Wymiennik AERO 4':'AERO 4 heat exchanger',
  'BIEG':'SPEED','CZERPNIA':'OUTDOOR','WYWIEW':'EXTRACT','WYRZUTNIA':'EXHAUST','NAWIEW':'SUPPLY',
  'WENTYLATOR':'FAN','Bieg':'Speed','Kominek':'Fireplace','Bez limitu':'Unlimited',
  'Tryb wentylacji':'Ventilation mode','Wietrzenie':'Boost','ODCZYT LOKALNY':'LOCAL DATA',
  'Połączono':'Connected','Brak raportu AERO':'No AERO report','niedostępne':'unavailable','brak odczytu':'no reading',
  'Brak odczytu':'No reading','Harmonogram':'Schedule','Ręcznie':'Manual','żądanie panelu Nano':'Nano request',
  'Aktywne':'Active','Wyłączone':'Off','Otwarty':'Open','Zamknięty':'Closed','wyłączone':'off','włączone':'on','żądanie:':'request:',
  'Symulacja · bez połączenia z centralą':'Demo · no device connection','Dane AERO 4 · szczegóły po kliknięciu':'AERO 4 data · click for details',
  'Oczekiwanie na aktualne dane':'Waiting for current data',
  'BYPASS OTWARTY':'BYPASS OPEN',
  'Bieg ·':'Speed ·',
  'Oczekiwanie na wysłanie':'Queued','Oczekiwanie na potwierdzenie':'Awaiting confirmation',
  'Zmiana niepotwierdzona':'Change not confirmed',
  'Wentylacja':'Ventilation','Bieg ręczny':'Manual speed','Urlop':'Holiday','Poza domem':'Away',
  'Harmonogram święto':'Holiday schedule','Automatyczny':'Automatic','GWC':'Ground exchanger',
  'Święto':'Holiday','Nastawa urządzenia':'Device setting','Praca z kominkiem':'Fireplace mode',
  'Odczyt nastaw':'Reading settings','Tryb pracy':'Operating mode','Funkcje dodatkowe':'Additional functions',
  'Włączanie…':'Turning on…','Wyłączanie…':'Turning off…','Zatrzymywanie…':'Stopping…','Oczekiwanie na odczyt obrotów':'Waiting for fan readings',
  'Włączona':'On','Wyłączona':'Off','Aktywne · bez limitu':'Active · unlimited',
  'Wyłącz wietrzenie':'Stop boost','Włącz wietrzenie bez limitu':'Start unlimited boost',
  'Filtr':'Filter','Reset licznika filtra':'Reset filter reminder counter',
  '% normy':'% of norm','Próg Nano':'Nano threshold','Brak progu odniesienia':'No reference threshold',
};
const DISPLAY = [
  ['header','Nagłówek','Header','header'],['connection','Stan połączenia','Connection status','#connection'],
  ['diagram','Schemat i temperatury','Diagram and temperatures','.machine'],['fans','Wentylatory','Fans','.fan'],
  ['filter','Filtr','Filter','#filter-status'],['air_co2','CO₂','CO₂','#air_co2-row'],
  ['air_pm25_percent','PM2,5','PM2.5','#air_pm25_percent-row'],['air_pm10_percent','PM10','PM10','#air_pm10_percent-row'],
  ['power','Wentylacja','Ventilation','.powerline'],['mode','Tryb pracy','Operating mode','#mode-select'],
  ['gear','Wybór biegu','Speed selection','#gear-control'],['fireplace','Kominek','Fireplace','#fireplace-control'],
  ['bypass','Bypass','Bypass','#bypass-control'],['gwc','GWC','Ground exchanger','#gwc-control'],
  ['boost','Wietrzenie','Boost','.boostbox'],['footer','Stopka','Footer','footer'],
];
function validateVisibility(value){
  if(value===undefined)return;
  if(!value||typeof value!=='object'||Array.isArray(value)||Object.values(value).some(v=>typeof v!=='boolean'))throw Error('visibility musi być mapą wartości true/false');
}
const css = `
:host{display:block;font-family:var(--paper-font-body1_-_font-family,system-ui,sans-serif);--ink:var(--primary-text-color,#e9f1f8);--muted:var(--secondary-text-color,#9aaec0);--line:var(--divider-color,#ffffff14);--accent:#39bdd3;--surface:color-mix(in srgb,var(--ink) 4%,var(--ha-card-background,var(--card-background-color,#111e2a)))}*{box-sizing:border-box}[hidden]{display:none!important}
ha-card{display:block;overflow:hidden;background:var(--ha-card-background,var(--card-background-color,#111e2a));border:1px solid var(--line);border-radius:20px;color:var(--ink);box-shadow:0 8px 28px #0000000c}
header{display:flex;justify-content:space-between;align-items:center;padding:22px 24px;gap:12px}.brand{font-size:10px;font-weight:700;letter-spacing:.16em;color:var(--muted);margin-bottom:6px}h2{margin:0;font-size:23px;font-weight:650;letter-spacing:-.04em}.connection{display:flex;align-items:center;gap:7px;border-radius:20px;font-size:11px;white-space:nowrap;background:#1aac8610;color:#32bd95;padding:8px 11px;border:1px solid #32bd951c}.connection i{width:6px;height:6px;background:currentColor;border-radius:50%}.connection.offline{color:var(--muted);background:#8b9cab12}
.machine{position:relative;background:radial-gradient(ellipse at 50% 48%,#173b4b 0,#112c3b 48%,#102431 100%);color:#eef7ff;border-top:1px solid #ffffff0a;border-bottom:1px solid #ffffff08}.machine:before{content:'';position:absolute;inset:0;background:linear-gradient(165deg,transparent 58%,#12c1dd07 58.3%,transparent 59%),linear-gradient(16deg,transparent 63%,#58d4fc0b 63.3%,transparent 64%);pointer-events:none}svg.diagram{display:block;width:100%;height:auto;position:relative}.duct-shadow{fill:none;stroke:#041626;stroke-width:29;stroke-linejoin:round;opacity:.45;transform:translateY(5px)}.duct{fill:none;stroke-width:23;stroke-linejoin:round;stroke-linecap:round}.shine{fill:none;stroke:#fff;stroke-width:1;opacity:.17}.flow{fill:none;stroke:#e1ffff;stroke-width:2;stroke-dasharray:2 15;stroke-linecap:round;opacity:0;animation:air 2.6s linear infinite;animation-play-state:paused}.flow.running{opacity:.65;animation-play-state:running}.arrow{fill:#49d6ee}.arrow.warm{fill:#ff647a}.tag{fill:#b7d6e7;font-size:11px;font-weight:600;letter-spacing:.09em}.temp{fill:#fff;font-size:33px;font-weight:650;letter-spacing:-.035em;font-variant-numeric:tabular-nums}.temp.missing{fill:#8aa9bc}.note{fill:#88abc2;font-size:10px}.core-label{fill:#bed7e8;font-size:9px;letter-spacing:.15em}.gear{fill:#fff;font-weight:650;font-size:23px}.status-core{fill:#9cc6d9;font-size:9px}.label-bg{fill:#071e32;opacity:.5}.core-body{fill:#0b2a43;stroke:#70cde347;stroke-width:1.3}.core-fin{stroke:#76a7c5;stroke-width:1;opacity:.22}.bypass{fill:none;stroke:#35d5e9;stroke-width:3;stroke-dasharray:4 5;opacity:0}.bypass.open{opacity:.8}
.fans{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;padding:18px 20px}.fan{display:flex;align-items:center;gap:12px;padding:14px 16px;border:1px solid var(--line);border-radius:12px;background:var(--surface)}.fan svg{width:32px;height:32px;flex-shrink:0;color:#39bdd3}.fan:nth-child(2) svg{color:#ed7a93}.rotor{transform-origin:20px 20px;animation:spin 3s linear infinite;animation-play-state:paused}.fan.running .rotor{animation-play-state:running}.fan-label{font-size:10px;font-weight:600;letter-spacing:.08em;color:var(--muted);margin-bottom:4px}.fan-value{font-size:24px;line-height:1.2;font-weight:600;font-variant-numeric:tabular-nums}.fan-value small{font-size:12px;color:var(--muted);font-weight:400}
.picker{padding:16px 12px;background:var(--ha-card-background,var(--card-background-color,#111e2a));min-width:0}select{width:100%;font:inherit;font-size:13px;font-weight:600;background:transparent;color:inherit;border:0;padding:0;min-height:24px}select option{background:var(--card-background-color,#111e2a);color:var(--primary-text-color,#e9f1f8)}.boost-row{grid-column:1/-1;display:grid;grid-template-columns:1fr 2fr;background:var(--card-background-color,#111e2a)}.presets{display:grid;grid-template-columns:repeat(3,1fr);gap:1px;background:var(--line)}.presets button{text-align:center;padding-inline:4px;white-space:nowrap;font-size:13px}.temperature-link{cursor:pointer}.temperature-link:focus{outline:none}.temperature-link[data-keyboard-focus]{outline:2px solid #39bdd3;outline-offset:4px}#action-status:empty{display:none}#action-status{padding:10px 16px;font-size:12px;color:var(--muted)}.states{display:grid;grid-template-columns:.8fr 1.4fr .8fr;gap:1px;background:var(--line);border-block:1px solid var(--line)}button{font:inherit;color:inherit;border:0;background:var(--ha-card-background,var(--card-background-color,#111e2a));padding:16px 12px;text-align:left;min-width:0;cursor:pointer}button:disabled{cursor:default}button:not(:disabled):hover{filter:brightness(1.08)}button:focus-visible{outline:2px solid #39bdd3;outline-offset:-3px}.state-label{color:var(--muted);font-size:10px;display:block;margin-bottom:6px}.state-value{font-size:13px;font-weight:600;display:block;white-space:normal;overflow-wrap:anywhere}.state-detail{font-size:9px;color:var(--muted);margin-top:5px;display:block}.readout{border:0;padding:0;background:none;color:inherit;cursor:pointer}.readout:disabled{cursor:default}footer{font-size:10px;color:var(--muted);display:flex;justify-content:space-between;gap:12px;padding:13px 20px;line-height:1.5}.missing-note{color:var(--muted)}
@keyframes air{to{stroke-dashoffset:-68}}@keyframes spin{to{transform:rotate(360deg)}}@media(prefers-reduced-motion:reduce){.flow,.rotor{animation:none}.flow.running{stroke-dasharray:4 13}}@media(max-width:380px){header{padding:18px 16px 14px}h2{font-size:21px}.fans{padding:14px 12px;gap:8px}.fan{padding:10px;gap:9px}footer{padding:12px}.tag{font-size:19px}.temp{font-size:40px}.note{font-size:15px}.core-label{font-size:12px}}
`;
const controlsCss=`
@keyframes control-pending{0%,100%{opacity:1}50%{opacity:.55}}
.controls button.pending,.controls select.pending,.filter-reset.pending{animation:control-pending 2s ease-in-out infinite;opacity:1}
@media(prefers-reduced-motion:reduce){.controls button.pending,.controls select.pending,.filter-reset.pending{animation:none;outline:1px solid var(--muted);outline-offset:1px}}

.filter-status{grid-column:1/-1;display:grid;gap:6px;padding:0 2px;--filter-color:#747c85}.filter-summary{display:flex;align-items:center;gap:8px;font-size:10px;line-height:1.5;color:var(--muted)}.filter-caption{display:flex;align-items:center;gap:6px;min-width:0}.filter-caption>svg{width:13px;height:13px;flex-shrink:0}.filter-period{opacity:.75}.filter-days{margin-left:auto;color:var(--ink);font-variant-numeric:tabular-nums;white-space:nowrap}.filter-reset{display:inline-flex;align-items:center;justify-content:center;background:none;border:0;border-radius:5px;padding:0;width:26px;min-height:26px;color:var(--muted);flex-shrink:0}.filter-reset svg{width:14px;height:14px}.filter-reset:not(:disabled):hover{color:var(--ink);background:var(--surface);filter:none}.filter-reset:disabled{opacity:.4;cursor:default}.filter-reset:focus-visible{outline:2px solid var(--muted);outline-offset:2px}.filter-track{height:2px;border-radius:2px;background:var(--line);overflow:hidden}.filter-track>i{display:block;height:100%;background:var(--filter-color);border-radius:inherit;transition:width .25s,background .25s}.filter-status[data-level=warning]{--filter-color:#d7b25e}.filter-status[data-level=danger],.filter-status[data-level=critical]{--filter-color:#ed737c}.filter-status[data-level=warning] .filter-days,.filter-status[data-level=danger] .filter-days,.filter-status[data-level=critical] .filter-days{color:var(--filter-color)}.filter-status[data-level=critical] .filter-track{background:#ed737c28;animation:filter-alert 1.6s ease-in-out infinite alternate}.filter-status[data-level=critical] .filter-reset{color:var(--filter-color)}
.air-quality[hidden],.air-quality .filter-track[hidden]{display:none}.air-quality{padding-top:2px}.air-quality .filter-summary{min-height:26px}.air-summary{width:100%;padding:0;background:none;border:0;text-align:left;cursor:pointer;font-family:inherit}.air-summary:focus-visible{outline:1px solid var(--muted);outline-offset:3px;border-radius:3px}.air-quality .filter-period{font-size:9px}.air-quality .filter-track>i{background:#747c85}
@keyframes filter-alert{from{opacity:1}to{opacity:.4}}@media(prefers-reduced-motion:reduce){.filter-status[data-level=critical] .filter-track{animation:none}.filter-track>i{transition:none}}

:host{--ui-surface:#24272b;--ui-muted:var(--muted);--ui-line:var(--line);--ui-accent:#aeb7c1}
.controls{padding:22px 22px 24px;background:var(--ha-card-background,var(--card-background-color,#111e2a));color:var(--ink);font-size:13px;font-family:inherit;border-top:1px solid var(--ui-line)}
.controls *{box-sizing:border-box}.controls button,.controls select{font:inherit;color:inherit;min-height:40px;cursor:pointer}
.controls button{padding:8px 12px;border:1px solid var(--ui-line);border-radius:9px;background:transparent;transition:background .15s}
.controls button:hover{background:#ffffff09;filter:none}.controls button:focus-visible,.controls select:focus-visible{outline:2px solid var(--ui-accent);outline-offset:3px}
.controls svg{width:20px;height:20px;flex:none;color:#9ca9b5}.controls strong{font-weight:600;font-size:13px}.controls small{display:block;font-size:11px;color:var(--ui-muted);line-height:1.5}
.controls .powerline,.controls .line,.controls .hero-control,.controls .quick-boost{display:flex;align-items:center;justify-content:space-between;gap:12px}
.controls .row-title{display:flex;align-items:center;gap:10px}.controls .row-title .subtle{margin-left:2px}.controls .label{font-weight:500}.controls .subtle{font-size:11px;color:var(--ui-muted)}
.controls .tiny,.controls .section-title{font-size:9px;letter-spacing:.12em;font-weight:600;color:var(--ui-muted)}
.controls select{width:auto;max-width:190px;border:0;background:transparent;padding:8px 25px 8px 10px;appearance:none;background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath d='m3 4.5 3 3 3-3' fill='none' stroke='%239ca5af' stroke-width='1.4'/%3E%3C/svg%3E");background-repeat:no-repeat;background-position:right 4px center;font-weight:500}
.controls select option{background:#24272b}.controls .switch{flex:none;width:40px;min-height:24px;height:24px;border:0;border-radius:20px;background:#474c53;padding:3px;position:relative}
.controls .switch i{display:block;width:18px;height:18px;background:#c2c7cd;border-radius:50%;transition:transform .15s}.controls .switch[aria-checked=true]{background:var(--ui-accent)}.controls .switch[aria-checked=true] i{background:#123a36;transform:translateX(16px)}
.controls .segments{display:flex;gap:4px;padding:4px;background:color-mix(in srgb,var(--ink) 1%,var(--ha-card-background,var(--card-background-color,#111e2a)));border:1px solid #ffffff09;border-radius:10px}.controls .segments button{flex:1;padding:6px 9px;min-height:34px;border:0;color:var(--muted);text-align:center;font-size:12px;white-space:nowrap}.controls .segments button[aria-pressed=true]{background:var(--surface);color:var(--ink);box-shadow:0 1px 4px #0003}
.controls .boostbox{padding:15px;background:var(--surface);border:1px solid #ffffff09;border-radius:12px;margin-top:18px}.controls .boostbox .line{margin-bottom:12px;min-height:20px}.controls .boostbox svg,.controls .quick-boost svg{color:var(--ui-accent)}.controls .boost-status{font-size:11px;color:var(--ui-muted)}.controls .end-boost{margin-top:10px;width:100%;min-height:32px;color:#a8f1df}.controls [hidden]{display:none!important}
.p1 .powerline{padding-bottom:18px;border-bottom:1px solid var(--ui-line);margin-bottom:6px}.p1 .power-caption{margin-top:3px;color:var(--ui-accent)}.p1 .line{min-height:52px}.p1 .section-title{margin:22px 0 4px}.p1 .line .segments{width:234px}.p1 .boostbox .line{min-height:20px}.p1 .boostbox{margin-top:12px}
@media(max-width:400px){.controls{padding:18px 16px 20px}.p1 .line .segments{width:198px}.controls .segments button{padding:6px}.controls .row-title .subtle{display:none}}

.controls{display:block}.controls .power-caption{margin-top:3px;color:var(--muted)}.controls .switch[aria-checked=true]{background:#747c86}.controls .switch[aria-checked=true] i{background:#252a30}
.controls .segments button[aria-pressed=true]{box-shadow:inset 0 0 0 1px var(--line),0 1px 3px #0003}
.controls .boostbox{border-color:var(--line)}.controls .boostbox svg{color:#aab5c1}
.p1 .line .state-segments{width:auto;min-width:160px}.p1 .line .state-segments button{min-width:46px}
.p1 .line .state-segments.two-state{min-width:110px}
.controls [data-stale=true],.fan.stale{opacity:.55}.controls .boost-toggle{border-left:1px solid var(--line)!important;border-radius:0 7px 7px 0;font-weight:600}.controls .boost-toggle #boost-countdown{display:block;margin-top:3px;text-align:center;color:var(--muted);font-size:10px;font-weight:400;line-height:1.2;font-variant-numeric:tabular-nums}.controls .boost-toggle[aria-pressed=true]{background:transparent;color:var(--ink)}
.controls button:disabled,.controls select:disabled{opacity:.55;cursor:default}.controls select option{background:var(--ha-card-background,var(--card-background-color,#111e2a));color:var(--ink)}
.controls .state-detail{margin:0;font-size:10px;color:var(--muted)}.controls .state-detail:empty{display:none}.controls .boostbox .state-detail{font-size:11px}.controls .line .segments{flex-shrink:0}
.controls .mode-label{font-size:13px;font-weight:500}.controls .row-title{font-size:13px}.controls select{min-height:40px}
@media(max-width:400px){.p1 .line .state-segments{min-width:150px}.p1 .line .state-segments button{min-width:43px}.p1 .line .state-segments.two-state{min-width:110px}}
`;
const bypassPath='M67 115H165Q183 115 183 133V256Q183 274 201 274H399Q417 274 417 256V247Q417 229 435 229H533';
const bypassCss=`.bypass{stroke-width:17;stroke-dasharray:none;stroke-linecap:round;stroke-linejoin:round;transition:opacity .25s}.bypass.open{opacity:1;filter:drop-shadow(0 0 5px #24d1e64d)}.machine.bypass-open #fresh-duct{opacity:.12}.machine.bypass-open #supply-arrow{fill:#35d5e9}.bypass-label{opacity:0}.bypass-label.open{opacity:1}.bypass-label rect{fill:#103c52;stroke:#35d5e980}.bypass-label text{fill:#6de9ed;font-size:11px;font-weight:650;letter-spacing:.07em}`;
// Inherit HA theme variables directly so theme changes also work without a hass update.
const themeCss=`
:host{--ink:var(--primary-text-color,#212121);--muted:var(--secondary-text-color,#727272);--line:var(--divider-color,#e0e0e0);--accent:var(--primary-color,#03a9f4);--card:var(--ha-card-background,var(--card-background-color,#fff));--surface:color-mix(in srgb,var(--ink) 5%,var(--card));--ui-accent:var(--accent)}
ha-card{background:var(--card);border:var(--ha-card-border-width,1px) solid var(--ha-card-border-color,var(--line));border-radius:var(--ha-card-border-radius,12px);box-shadow:var(--ha-card-box-shadow,none)}
.machine{background:radial-gradient(ellipse at 50% 48%,color-mix(in srgb,var(--accent) 12%,var(--card)),var(--card));color:var(--ink);border-color:var(--line)}
.machine:before{display:none}.tag,.core-label,.note,.status-core{fill:var(--muted)}.temp,.gear{fill:var(--ink)}.temp.missing{fill:var(--muted)}
.core-body{fill:var(--surface);stroke:var(--line)}.core-fin{stroke:var(--muted)}.diagram rect[x="250"]{fill:var(--card);stroke:var(--line)}
.bypass-label rect{fill:var(--card);stroke:var(--accent)}.bypass-label text{fill:var(--ink)}
.controls,.picker,button,.boost-row{background:var(--card)}.controls svg,.controls .boostbox svg{color:var(--muted)}
.controls button:hover{background:var(--surface)}.controls .segments{border-color:var(--line)}
.controls .switch{background:var(--disabled-color,#bdbdbd)}.controls .switch i{background:var(--card)}
.controls .switch[aria-checked=true]{background:var(--accent)}.controls .switch[aria-checked=true] i{background:var(--text-primary-color,#fff)}
.controls .segments button[aria-pressed=true]{background:color-mix(in srgb,var(--accent) 14%,var(--card));color:var(--ink);box-shadow:inset 0 0 0 1px var(--accent)}
.controls .boost-toggle[aria-pressed=true]{background:color-mix(in srgb,var(--accent) 14%,var(--card))}
.connection{color:var(--success-color,#208349);background:color-mix(in srgb,var(--success-color,#208349) 10%,var(--card));border-color:var(--line)}
.connection.offline{color:var(--muted);background:var(--surface)}
.filter-status[data-level=warning]{--filter-color:var(--warning-color,#9c6a00)}.filter-status[data-level=danger],.filter-status[data-level=critical]{--filter-color:var(--error-color,#db4437)}
.fans:has(>.fan[hidden]){grid-template-columns:1fr}
`;

export class Aero4Card extends HTMLElement {
  constructor(){super();this.attachShadow({mode:'open'});this._demo={...DEMO};this._choices={};this._timers={};this._busy=false;this._pending={};this._confirmed={};this._onKeyboard=()=>this._keyboardInput=true;this._onPointer=()=>this._keyboardInput=false;}
  connectedCallback(){clearInterval(this._countdownInterval);this._countdownInterval=setInterval(()=>this._updateBoostCountdown(),1000);this._updateBoostCountdown();document.addEventListener('keydown',this._onKeyboard,true);document.addEventListener('pointerdown',this._onPointer,true);}
  disconnectedCallback(){clearInterval(this._countdownInterval);this._countdownInterval=null;this._cancelChoices();document.removeEventListener('keydown',this._onKeyboard,true);document.removeEventListener('pointerdown',this._onPointer,true);}
  _cancelChoices(){this._epoch=(this._epoch??0)+1;for(const p of Object.values(this._pending??{})){clearTimeout(p.timer);p.cancelDelay?.();}this._pending={};this._busy=false;this._choices={};}

  setConfig(config){
    if(!config || (config.demo!==undefined && typeof config.demo!=='boolean')) throw Error('demo musi być true/false');
    if(config.entities!==undefined && (!config.entities || typeof config.entities!=='object' || Array.isArray(config.entities))) throw Error('entities musi być mapą');
    validateVisibility(config.visibility);
    this._cancelChoices();
    this._confirmed={};this._config={...config,entities:{...config.entities},visibility:{...config.visibility}};
    if(config.demo) this._demo={...DEMO};
    this._build();this._update();
  }
  set hass(value){this._hass=value;this._resolveEntities();this._update();}
  getCardSize(){return Math.max(1,Math.ceil((this.shadowRoot.querySelector('ha-card')?.offsetHeight||350)/50));}
  getGridOptions(){return {columns:12,rows:'auto',min_columns:6,min_rows:1};}
  static getStubConfig(){return {type:'custom:aero4-card'};}
  static getConfigElement(){return document.createElement('aero4-card-editor');}
  _applyVisibility(){
    const visible=key=>this._config.visibility?.[key]!==false;
    for(const [key,,,selector] of DISPLAY){
      for(let el of this.shadowRoot.querySelectorAll(selector)){
        if(['mode','gear','fireplace','bypass','gwc'].includes(key))el=el.closest('.line');
        const unavailable=key.startsWith('air_')&&(this._number(key)===null||this._number(key)<0||!this._ready(key));
        el.hidden=!visible(key)||unavailable;
      }
    }
    this.shadowRoot.querySelector('.fans').hidden=![...this.shadowRoot.querySelector('.fans').children].some(el=>!el.hidden);
    this.shadowRoot.querySelector('.controls').hidden=!['power','mode','gear','fireplace','bypass','gwc','boost'].some(visible);
    this.shadowRoot.querySelector('.section-title').hidden=!['fireplace','bypass','gwc'].some(visible);
  }
  get _language(){return String(this._hass?.locale?.language??this._hass?.language??'en').toLowerCase().startsWith('pl')?'pl':'en';}
  _translate(value){
    if(this._language==='pl')return String(value);
    let result=String(value);for(const key of Object.keys(EN).sort((a,b)=>b.length-a.length))result=result.replaceAll(key,EN[key]);
    return result;
  }
  _resolveEntities(){
    if(!this._config) return;
    this._resolved={...this._config.entities};
                                                                               
    if(!this._registry && !this._registryRequested && this._hass?.callWS){
      this._registryRequested=true;
      this._hass.callWS({type:'config/entity_registry/list'}).then(entries=>{
        this._registry=entries;this._update();
      }).catch(()=>{                                                                });
    }
    const entries=(this._registry??[]).filter(e=>e.platform==='compit_aero4');
    const device=this._config.device;
    const candidates=device ? entries.filter(e=>e.device_id===device) : entries;
    const devices=new Set(candidates.map(e=>e.device_id));
    if(devices.size!==1) return;
    for(const key of KEYS){
      if(this._resolved[key]) continue;
      const controlDomain={parameter_ventilation_enabled:'switch',parameter_gwc_mode:'select',parameter_filter_reminder_period:'number',
        parameter_holiday_mode:'switch',parameter_away_mode:'switch',parameter_fireplace_active:'switch'}[key];
      const match=candidates.find(e=>!e.disabled_by && e.unique_id?.endsWith(`_${key}`)
        && (!controlDomain || e.entity_id?.startsWith(`${controlDomain}.`)));
      if(match) this._resolved[key]=match.entity_id;
    }
  }
  _state(key){return this._config?.demo ? this._demo[key]??'unknown' : this._hass?.states?.[(this._resolved??this._config?.entities??{})[key]]?.state??'unknown';}
  _updateBoostCountdown(){
    const el=this.shadowRoot.getElementById('boost-countdown');if(!el)return;
    const id=(this._resolved??this._config?.entities??{}).boost_control;
    const attributes=this._hass?.states?.[id]?.attributes??{};
    const deadline=attributes.boost_deadline;
    const visible=this._state('boost_control')==='on'&&typeof deadline==='number'&&Number.isFinite(deadline);
    el.hidden=!visible;
    if(visible){const seconds=Math.max(0,Math.ceil(deadline-Date.now()/1000));el.textContent=`${Math.floor(seconds/60)}:${String(seconds%60).padStart(2,'0')}`;}
    else el.textContent='';
  }
  _shown(key){const value=this._state(key);if(!['unknown','unavailable'].includes(value)){this._confirmed[key]=value;return value;}return this._confirmed[key]??value;}
  _shownNumber(key){const v=this._shown(key);if(v===null||String(v).trim()==='')return null;const n=Number(v);return Number.isFinite(n)?n:null;}
  _number(key){const v=this._state(key);if(v===null || String(v).trim()==='')return null;const n=Number(v);return Number.isFinite(n)?n:null;}
  _text(id,text){this.shadowRoot.getElementById(id).textContent=id==='title'?text:this._translate(text);}
  _temperature(key){
    const n=this._shownNumber(key),entity=(this._resolved??this._config.entities)[key];
    const unit=this._hass?.states?.[entity]?.attributes?.unit_of_measurement??'°C';
    return n===null?'—':`${n.toLocaleString(this._language==='pl'?'pl-PL':'en-GB',{minimumFractionDigits:1,maximumFractionDigits:1})}${unit}`;
  }
  _more(key){
    if(this._config.demo) return;
    const entityId=(this._resolved??this._config.entities)[key];
    if(entityId && this._hass?.states?.[entityId]) this.dispatchEvent(new CustomEvent('hass-more-info',{detail:{entityId},bubbles:true,composed:true}));
  }
  _build(){
    this._builtLanguage=this._language;
    const markup=`<style>${css}${bypassCss}${controlsCss}${themeCss}</style><ha-card>
      <header><div><div class="brand">C14 · REKUPERACJA</div><h2 id="title"></h2></div><div id="connection" class="connection"><i></i><span id="connection-label"></span></div></header>
      <div class="machine"><svg class="diagram" viewBox="0 0 600 340" role="img" aria-labelledby="drawing-title drawing-desc">
      <title id="drawing-title">Wymiennik AERO 4</title><desc id="drawing-desc">Czerpnia u góry po lewej, nawiew na dole po prawej. Wywiew u góry po prawej, wyrzutnia na dole po lewej. Dwa oddzielne kanały wymiany ciepła.</desc>
      <defs><linearGradient id="fresh" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#23d0d8"/><stop offset=".48" stop-color="#497eaf"/><stop offset="1" stop-color="#ef557a"/></linearGradient><linearGradient id="used" x1="1" y1="0" x2="0" y2="1"><stop stop-color="#eec64d"/><stop offset=".5" stop-color="#9485b2"/><stop offset="1" stop-color="#79cbe2"/></linearGradient><mask id="bypass-crossing"><rect width="600" height="340" fill="white"/><rect x="165" y="214" width="36" height="30" fill="black"/></mask></defs>
      <circle cx="300" cy="172" r="89" fill="#1a5574" opacity=".3"/><circle cx="300" cy="172" r="80" fill="none" stroke="#7bc1e3" opacity=".12"/>
      <path class="core-body" d="M300 88L384 172L300 256L216 172Z"/>
      ${Array.from({length:11},(_,i)=>`<path class="core-fin" d="M${258+i*5} ${130-i*2}L${300+i*5} ${214-i*2}"/>`).join('')}
      <path class="duct-shadow" d="M67 115H226L374 229H533M533 115H374L226 229H67"/>
      <path id="bypass-guide" class="bypass" d="${bypassPath}"/>
      <path class="duct" stroke="url(#used)" d="M533 115H374L226 229H67"/>
      <path id="fresh-duct" class="duct" stroke="url(#fresh)" d="M67 115H226L374 229H533"/>
      <path class="shine" d="M67 104H229L378 218H533M533 104H371L222 218H67"/>
      <path id="fresh-flow" class="flow" d="M67 115H226L374 229H533"/>
      <path id="used-flow" class="flow" d="M533 115H374L226 229H67"/>
      <path id="bypass-flow" class="flow" mask="url(#bypass-crossing)" d="${bypassPath}"/>
      <path class="arrow" d="M43 103L59 115L43 127Z M55 217L39 229L55 241Z"/><path class="arrow warm" d="M557 103L541 115L557 127Z"/><path id="supply-arrow" class="arrow warm" d="M545 217L561 229L545 241Z"/>
      <g id="bypass-label" class="bypass-label" aria-hidden="true"><rect x="220" y="291" width="160" height="23" rx="11"/><text x="300" y="307" text-anchor="middle">BYPASS OTWARTY</text></g>
      <rect x="250" y="145" width="100" height="54" rx="12" fill="#0c2c47" stroke="#80b6d82b"/>
      <text x="300" y="160" text-anchor="middle" class="core-label">BIEG</text><text x="300" y="186" text-anchor="middle" class="gear" id="gear"></text>
      <g transform="translate(30 42)"><text class="tag">CZERPNIA</text><text class="temp" id="outdoor_temperature" y="38"></text><text class="note" id="outdoor_temperature-note" y="54"></text></g>
      <g transform="translate(570 42)" text-anchor="end"><text class="tag">WYWIEW</text><text class="temp" id="extract_temperature" y="38"></text><text class="note" id="extract_temperature-note" y="54"></text></g>
      <g transform="translate(30 276)"><text class="tag">WYRZUTNIA</text><text class="temp" id="exhaust_temperature" y="38"></text><text class="note" id="exhaust_temperature-note" y="53"></text></g>
      <g transform="translate(570 276)" text-anchor="end"><text class="tag">NAWIEW</text><text class="temp" id="supply_temperature" y="38"></text><text class="note" id="supply_temperature-note" y="53"></text></g>
      </svg></div>
      <div class="fans">${[['a','NAWIEW'],['b','WYWIEW']].map(([k,label])=>`<div class="fan" id="fan-${k}">${fan}<div><div class="fan-label">${label}</div><div class="fan-value" id="fan-${k}-value"></div></div></div>`).join('')}</div>
      <div class="controls p1">
      <div class="powerline"><div class="row-title"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3v9M6 5.5a9 9 0 1 0 12 0"/></svg><div><strong>Wentylacja</strong><small class="power-caption" id="power-value"></small></div></div><button id="power-control" type="button" class="switch" role="switch" aria-checked="false" aria-label="Wentylacja"><i></i></button></div>
      <div class="line"><label class="mode-label" for="mode-select">Tryb pracy</label><select id="mode-select" aria-label="Tryb wentylacji"><option value="schedule">Harmonogram</option><option value="manual">Ręcznie</option><option value="holiday">Urlop</option><option value="away">Poza domem</option></select></div>
      <div class="line"><span class="mode-label" id="gear-label">Bieg</span><div class="segments" id="gear-control" role="group" aria-labelledby="gear-label">${[['stopped','STOP'],['B1','B1'],['B2','B2'],['B3','B3']].map(([value,label])=>`<button type="button" data-gear="${value}" aria-pressed="false">${label}</button>`).join('')}</div></div>
      <div class="section-title">Funkcje dodatkowe</div>
      ${[['fireplace','Kominek',"<svg viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.6\" stroke-linecap=\"round\" stroke-linejoin=\"round\" aria-hidden=\"true\"><path d=\"M13 3c1 5-5 6-3 11-3-1-3-4-3-4-7 10 5 15 10 9 5-6-2-9-4-16Z\"/></svg>",['off','on']],['bypass','Bypass',"<svg viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.6\" stroke-linecap=\"round\" stroke-linejoin=\"round\" aria-hidden=\"true\"><path d=\"M3 7h5c5 0 3 10 8 10h5m-4-4 4 4-4 4M3 17h5c5 0 3-10 8-10h5m-4-4 4 4-4 4\"/></svg>",['OFF','ON','AUTO']],['gwc','GWC',"<svg viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.6\" stroke-linecap=\"round\" stroke-linejoin=\"round\" aria-hidden=\"true\"><path d=\"M3 7h18M5 11v5a3 3 0 0 0 6 0v-2a3 3 0 0 1 6 0v2h4M7 3v4m10-4v4\"/></svg>",['off','auto']]].map(([key,label,icon,options])=>`<div class="line"><div class="row-title">${icon}<div><span id="${key}-label">${label}</span><span class="state-detail" id="${key}-detail"></span></div></div><div class="segments state-segments ${options.length===2?'two-state':''}" id="${key}-control" role="group" aria-labelledby="${key}-label">${options.map(value=>`<button type="button" data-choice="${key}" data-value="${value}" aria-pressed="false">${value.toUpperCase()}</button>`).join('')}</div></div>`).join('')}
      <div class="boostbox"><div class="line"><span class="row-title"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 8h12a3 3 0 1 0-3-3M3 12h16a3 3 0 1 1-3 3M3 16h5a3 3 0 1 1-3 3"/></svg><strong>Wietrzenie</strong></span><span id="boost-detail" class="state-detail" aria-live="polite"></span></div><div class="segments" role="group" aria-label="Wietrzenie">${['15','30','60'].map(n=>`<button type="button" data-minutes="${n}" aria-pressed="false">${n} min</button>`).join('')}<button id="boost-control" class="boost-toggle" type="button" aria-pressed="false"><span id="boost-value"></span><small id="boost-countdown" hidden></small></button></div></div>
      </div><div id="action-status" role="status" aria-live="polite"></div>
      <footer><span id="footer-status"></span><span>ODCZYT LOKALNY</span></footer></ha-card>`;
    this.shadowRoot.innerHTML=this._translate(markup);
    this.shadowRoot.querySelector('.fans').insertAdjacentHTML('beforeend',`<div class="filter-status" id="filter-status" data-level="unknown"><div class="filter-summary"><span class="filter-caption"><svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.2" aria-hidden="true"><rect x="3" y="3" width="14" height="14" rx="2"/><path d="M7 6v8m3-8v8m3-8v8"/></svg><span>${this._translate('Filtr')}</span><span class="filter-period" id="filter-period"></span></span><span class="filter-days" id="filter-value"></span><button type="button" class="filter-reset" id="filter-reset"><svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M15.3 6A6 6 0 1 0 16 12M16 3v4h-4"/></svg></button></div><div class="filter-track" id="filter-track" role="progressbar" aria-valuemin="0" aria-valuemax="100"><i id="filter-fill"></i></div></div>`);
    for(const [key,label] of [['air_co2','CO₂'],['air_pm25_percent','PM2,5'],['air_pm10_percent','PM10']]){
      this.shadowRoot.querySelector('.fans').insertAdjacentHTML('beforeend',`<div class="filter-status air-quality" id="${key}-row" hidden><button class="filter-summary air-summary" type="button" id="${key}-info"><span class="filter-caption"><svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.2" aria-hidden="true"><circle cx="5" cy="10" r="2"/><circle cx="12" cy="5" r="2"/><circle cx="14" cy="14" r="3"/></svg><span>${label}</span><span class="filter-period" id="${key}-reference"></span></span><span class="filter-days" id="${key}-value"></span></button><div class="filter-track" id="${key}-track" role="meter" aria-label="${label}" aria-valuemin="0" aria-valuemax="100"><i id="${key}-fill"></i></div></div>`);
      this.shadowRoot.getElementById(`${key}-info`).onclick=()=>this._more(key);
    }
    this.shadowRoot.getElementById('filter-reset').onclick=()=>{
      if(this._config.demo||this._controlBusy('filter')||this._number('filter_days_remaining')===null||!this._filterResetReady())return;
      this._execute(()=>this._service('button','press',{entity_id:this._resolved.filter_reset}),{key:'filter',value:'reset'});
    };
    this.shadowRoot.onkeydown=()=>this._keyboardInput=true;
    this.shadowRoot.onpointerdown=()=>this._keyboardInput=false;
    this.shadowRoot.getElementById('power-control').onclick=()=>{const value=this._state('parameter_ventilation_enabled')==='on'?'off':'on';this._execute(()=>this._switch('parameter_ventilation_enabled',value==='on'),{key:'power',value});};
    this.shadowRoot.getElementById('mode-select').onchange=e=>{const value=e.target.value;this._execute(()=>this._user('mode',value),{key:'mode',value});};
    for(const button of this.shadowRoot.querySelectorAll('[data-gear]'))button.onclick=()=>this._execute(()=>this._user('gear',button.dataset.gear),{key:'gear',value:button.dataset.gear});
    for(const button of this.shadowRoot.querySelectorAll('[data-choice]'))button.onclick=()=>this._choose(button.dataset.choice,button.dataset.value);
    this.shadowRoot.getElementById('boost-control').onclick=()=>{const value=this._state('boost_control')==='on'||this._pendingFor('boost')&&this._pendingFor('boost').value!=='off'?'off':'unlimited';this._execute(()=>this._user('boost',value),{key:'boost',value});};
    for(const button of this.shadowRoot.querySelectorAll('[data-minutes]'))button.onclick=()=>this._execute(()=>this._user('boost',button.dataset.minutes),{key:'boost',value:button.dataset.minutes});
    for(const key of ['outdoor_temperature','supply_temperature','extract_temperature','exhaust_temperature']){
      const el=this.shadowRoot.getElementById(key).parentElement;el.classList.add('temperature-link');el.setAttribute('role','button');el.setAttribute('tabindex','0');el.setAttribute('aria-label',key.replaceAll('_',' '));el.onclick=()=>{el.removeAttribute('data-keyboard-focus');el.blur();this._more(key);};el.onfocus=()=>{if(this._keyboardInput)el.setAttribute('data-keyboard-focus','');};el.onblur=()=>el.removeAttribute('data-keyboard-focus');el.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();el.setAttribute('data-keyboard-focus','');this._more(key);}};
    }
  }
  _ready(key){return !!this._resolved?.[key]&&!['unknown','unavailable'].includes(this._state(key));}
  _filterResetReady(){
    const state=this._hass?.states?.[this._resolved?.filter_reset];
                                                                             
    return !!state&&state.state!=='unavailable'&&!state.attributes?.pending&&!!(this._hass?.callWS||this._hass?.callService);
  }
  _service(domain,service,data){
                                                                                            
    if(this._hass.callWS)return this._hass.callWS({type:'call_service',domain,service,service_data:data});
    return this._hass.callService(domain,service,data);
  }
  _call(key,service,data={}){
    if(!this._ready(key))throw Error(this._translate('niedostępne'));
    const entity_id=this._resolved[key];
    return this._service(entity_id.split('.')[0],service,{entity_id,...data});
  }
  _switch(key,on){return this._call(key,on?'turn_on':'turn_off');}
  _user(action,value){
    const entity_id=this._resolved.parameter_ventilation_enabled??this._resolved.operating_mode;
    if(!entity_id)throw Error(this._translate('niedostępne'));
    return this._service('compit_aero4','user_control',{entity_id,action,value});
  }
  _pendingFor(key){const p=this._pending?.[key];return p?.epoch===this._epoch?p:null;}
  _queueState(){
    const ids=[this._resolved?.parameter_ventilation_enabled,this._resolved?.boost_control];
    return ids.map(id=>this._hass?.states?.[id]?.attributes?.control_queue).find(q=>q?.active||q?.pending?.length)??{};
  }
  _controlBusy(key){
    const p=this._pendingFor(key);if(!p?.sent)return false;
    const group={mode:'ventilation',gear:'ventilation'}[key]??key,q=this._queueState();
    if(q.active?.group===group)return true;
    if(q.pending?.some(r=>r.group===group))return false;
    return true;
  }
  async _execute(operation,selection,delay=0){
    if(this._config.demo)return;
    const key=selection.key,stop=['power','boost'].includes(key)&&selection.value==='off';
    if(this._controlBusy(key)&&!stop)return;
    const old=this._pendingFor(key);if(old&&!old.sent){clearTimeout(old.timer);old.cancelDelay?.();}
    const pending={...selection,epoch:this._epoch,sent:false};
    this._pending[key]=pending;this._busy=true;this._update();
    try{
      if(delay)await new Promise(resolve=>{pending.cancelDelay=resolve;pending.timer=setTimeout(resolve,delay);});
      clearTimeout(pending.timer);pending.cancelDelay=null;
      if(!this.isConnected||pending.epoch!==this._epoch||this._pending[key]!==pending)return;
      pending.sent=true;this._update();
      await operation();
    }catch{
                                                                                  
    }finally{
      if(this._pending[key]===pending){delete this._pending[key];this._busy=Object.keys(this._pending).length>0;this._update();}
    }
  }
  _choose(key,value){
    if(this._controlBusy(key)||this._config.demo)return;
    const field={bypass:'bypass_mode',fireplace:'parameter_fireplace_active',gwc:'parameter_gwc_mode'}[key];
    const options={bypass:['ON','OFF','AUTO'],fireplace:['on','off'],gwc:['off','auto']}[key];
    if(!options?.includes(value)||!this._ready(field))return;
    if(value===this._state(field)&&!this._pendingFor(key))return;
    return this._execute(()=>key==='fireplace'?this._switch(field,value==='on'):this._call(field,'select_option',{option:value}),{key,value},400);
  }
  _update(){
    if(!this._config) return;
    if(this._builtLanguage!==this._language)this._build();
    this._resolveEntities();
    this._text('title',this._config.title??'AERO 4');
    const online=this._state('aero_online')==='on';
    const pendings=Object.values(this._pending??{}).filter(p=>p.epoch===this._epoch);
    const filterDays=this._number('filter_days_remaining'),filterPeriod=this._number('parameter_filter_reminder_period');
    const filter=this.shadowRoot.getElementById('filter-reset'),filterStatus=this.shadowRoot.getElementById('filter-status'),track=this.shadowRoot.getElementById('filter-track');
    const dayUnit=n=>this._language==='pl'?(n===1?'dzień':'dni'):(n===1?'day':'days');
    const filterLabel=filterDays===null?'—':`${filterDays} ${dayUnit(filterDays)}`;
    this.shadowRoot.getElementById('filter-value').textContent=filterLabel;
    this.shadowRoot.getElementById('filter-period').textContent=filterPeriod!==null&&filterPeriod>0?`· ${this._language==='pl'?'co':'every'} ${filterPeriod} ${dayUnit(filterPeriod)}`:'· —';
    const percentage=filterDays!==null&&filterPeriod!==null&&filterPeriod>0?Math.max(0,Math.min(100,filterDays/filterPeriod*100)):null;
    filterStatus.dataset.level=percentage===null?'unknown':percentage<=5?'critical':percentage<=10?'danger':percentage<=30?'warning':'normal';
    this.shadowRoot.getElementById('filter-fill').style.width=`${percentage??0}%`;
    if(percentage===null)track.removeAttribute('aria-valuenow');else track.setAttribute('aria-valuenow',String(Number(percentage.toFixed(2))));
    track.setAttribute('aria-label',this._translate('Filtr'));
    track.setAttribute('aria-valuetext',percentage===null?this._translate('Brak odczytu'):`${filterLabel}, ${Number(percentage.toFixed(1))}%`);
    filter.disabled=this._config.demo||this._controlBusy('filter')||filterDays===null||!this._filterResetReady();
    filter.title=this._translate('Reset licznika filtra');
    filter.setAttribute('aria-label',`${filter.title}. ${filterLabel}`);
    for(const key of ['air_co2','air_pm25_percent','air_pm10_percent']){
                                                                                 
      const n=this._number(key),available=n!==null&&n>=0&&this._ready(key);
      this.shadowRoot.getElementById(`${key}-row`).hidden=!available;
      const co2=key==='air_co2',threshold=this._number('parameter_sensor_co2_start');
      const reference=co2?(threshold!==null&&threshold>0?threshold:null):100;
      const unit=co2?'ppm':this._translate('% normy');
      const text=available?`${n.toLocaleString(this._language==='pl'?'pl-PL':'en-GB')} ${unit}`:'';
      this.shadowRoot.getElementById(`${key}-value`).textContent=text;
      this.shadowRoot.getElementById(`${key}-reference`).textContent=co2&&reference!==null?`· ${this._translate('Próg Nano')} ${reference} ppm`:'';
      const meter=this.shadowRoot.getElementById(`${key}-track`);
      meter.hidden=!available||reference===null;
      const ratio=available&&reference!==null?Math.max(0,Math.min(100,n/reference*100)):null;
      this.shadowRoot.getElementById(`${key}-fill`).style.width=`${ratio??0}%`;
      if(ratio===null)meter.removeAttribute('aria-valuenow');else meter.setAttribute('aria-valuenow',String(ratio));
      meter.setAttribute('aria-valuetext',text);
      this.shadowRoot.getElementById(`${key}-info`).title=co2&&reference===null?this._translate('Brak progu odniesienia'):text;
    }
    this._text('connection-label',this._config.demo?'DEMO':online?'Połączono':'Brak raportu AERO');
    this.shadowRoot.getElementById('connection').classList.toggle('offline',!online);
    for(const key of ['outdoor_temperature','supply_temperature','extract_temperature','exhaust_temperature']){
      const n=this._number(key);this._text(key,this._temperature(key));
      this.shadowRoot.getElementById(key).classList.toggle('missing',n===null);
      this._text(`${key}-note`,n!==null?'':this._shownNumber(key)!==null?'Ostatni odczyt':'brak odczytu');
    }
    const gear=this._shown('ventilation_requested');
    this._text('gear',gear==='stopped'?'STOP':/^B[123]$/.test(gear)?gear:'—');
    const speeds=[];
    for(const k of ['a','b']){
      const n=this._shownNumber(`fan_${k}_percent`),valid=n!==null&&n>=0&&n<=100;speeds.push(valid?n:null);
      this._text(`fan-${k}-value`,valid?`${n} %`:'—');
      const el=this.shadowRoot.getElementById(`fan-${k}`);el.classList.toggle('running',online&&valid&&n>0);el.classList.toggle('stale',this._number(`fan_${k}_percent`)===null);
      el.querySelector('.rotor').style.animationDuration=`${valid?Math.max(.6,4-n/30):4}s`;
    }
                                                                                  
    const supplyMoving=online&&speeds[0]!==null&&speeds[0]>0;
    const extractMoving=online&&speeds[1]!==null&&speeds[1]>0;
    this.shadowRoot.getElementById('fresh-flow').classList.toggle('running',supplyMoving&&this._state('bypass_reported_open')==='off');
    this.shadowRoot.getElementById('used-flow').classList.toggle('running',extractMoving);
    const bypassOpen=online&&this._state('bypass_reported_open')==='on';
    this.shadowRoot.querySelector('.machine').classList.toggle('bypass-open',bypassOpen);
    this.shadowRoot.getElementById('bypass-guide').classList.toggle('open',bypassOpen);
    this.shadowRoot.getElementById('bypass-label').classList.toggle('open',bypassOpen);
    this.shadowRoot.getElementById('bypass-label').setAttribute('aria-hidden',String(!bypassOpen));
    this.shadowRoot.getElementById('bypass-flow').classList.toggle('running',supplyMoving&&bypassOpen);
    for(const [id,index] of [['fresh-flow',0],['bypass-flow',0],['used-flow',1]]){
      this.shadowRoot.getElementById(id).style.animationDuration=`${speeds[index]!==null?Math.max(.6,4-speeds[index]/30):4}s`;
    }
    const mode=this._shown('parameter_holiday_mode')==='on'?'holiday':this._shown('parameter_away_mode')==='on'?'away':this._shown('operating_mode');
    this.shadowRoot.getElementById('mode-select').value=this._pendingFor('mode')?.value??(mode==='holiday_schedule'?'schedule':mode);
    const manual=this._shown('manual_speed');
                                                                                               
    const selectedGear=this._pendingFor('gear')?.value??(mode==='manual'&&['B1','B2','B3','stopped'].includes(manual)?manual:gear);
    for(const button of this.shadowRoot.querySelectorAll('[data-gear]'))button.setAttribute('aria-pressed',String(button.dataset.gear===selectedGear));
    const powerPending=this._pendingFor('power');
    const powered=powerPending?.value??this._shown('parameter_ventilation_enabled');
                                                                                     
    const freshSpeeds=['a','b'].map(k=>this._number(`fan_${k}_percent`));
    const stopped=online&&freshSpeeds.every(n=>n===0);
    const moving=online&&freshSpeeds.some(n=>n!==null&&n>0);
    const powerCaption=powerPending?(powered==='off'?'Wyłączanie…':'Włączanie…'):
      !this._ready('parameter_ventilation_enabled')&&['on','off'].includes(powered)?'Odświeżanie':
      powered==='on'?'Włączona':powered==='off'?(stopped?'Wyłączona':moving?'Zatrzymywanie…':'Oczekiwanie na odczyt obrotów'):'Brak odczytu';
    this._text('power-value',powerCaption);
    this.shadowRoot.getElementById('power-control').setAttribute('aria-checked',String(powered==='on'));
    for(const key of ['bypass','fireplace','gwc']){
      const state=this._pendingFor(key)?.value??this._shown({bypass:'bypass_mode',fireplace:'parameter_fireplace_active',gwc:'parameter_gwc_mode'}[key]);
      for(const button of this.shadowRoot.querySelectorAll(`[data-choice="${key}"]`))button.setAttribute('aria-pressed',String(button.dataset.value===state));
      const command=key==='bypass'?this._state('bypass_command_status'):null;
      this._text(`${key}-detail`,!this._ready({bypass:'bypass_mode',fireplace:'parameter_fireplace_active',gwc:'parameter_gwc_mode'}[key])&&['on','off','auto','ON','OFF','AUTO'].includes(state)?'Odświeżanie':!['on','off','auto','ON','OFF','AUTO'].includes(state)?'Brak odczytu':'');
    }
    const boost=this._state('boost_control')==='on',duration=this._number('parameter_boost_duration');
    this._text('boost-value',['off','unlimited'].includes(this._pendingFor('boost')?.value)?(this._pendingFor('boost').value==='off'?'OFF':'ON'):boost||this._pendingFor('boost')&&this._pendingFor('boost').value!=='off'?'OFF':'ON');
    this.shadowRoot.getElementById('boost-control').setAttribute('aria-pressed',String(boost));
    this.shadowRoot.getElementById('boost-control').setAttribute('aria-label',this._translate(boost?'Wyłącz wietrzenie':'Włącz wietrzenie bez limitu'));
    this._updateBoostCountdown();
    this._text('boost-detail',boost?(duration===0?'Aktywne · bez limitu':duration===null?'Aktywne':`Aktywne · ${duration} min`):this._state('boost_control')==='off'?'Wyłączone':'Brak odczytu');
    for(const button of this.shadowRoot.querySelectorAll('[data-minutes]'))button.setAttribute('aria-pressed',String(this._pendingFor('boost')?button.dataset.minutes===this._pendingFor('boost').value:boost&&Number(button.dataset.minutes)===duration));
    const required={power:['parameter_ventilation_enabled'],mode:['operating_mode','parameter_holiday_mode','parameter_away_mode'],gear:['operating_mode','parameter_holiday_mode','parameter_away_mode'],bypass:['bypass_mode'],fireplace:['parameter_fireplace_active'],gwc:['parameter_gwc_mode'],boost:['boost_control','parameter_boost_duration']};
    for(const [key,keys] of Object.entries(required)){
      let disabled=this._config.demo||this._controlBusy(key)||!(this._hass?.callWS||this._hass?.callService)||keys.some(k=>!this._ready(k));
      if(key==='power'&&this._state('parameter_ventilation_enabled')==='on')disabled=this._config.demo||keys.some(k=>!this._ready(k));
      const control=this.shadowRoot.getElementById(key==='mode'?'mode-select':`${key}-control`);
      control.dataset.stale=String(keys.some(k=>!this._ready(k)));
      if(control.matches('button,select'))control.disabled=disabled;
      else for(const button of control.querySelectorAll('button'))button.disabled=disabled;
      if(key==='boost'){for(const el of this.shadowRoot.querySelectorAll('[data-minutes]'))el.disabled=disabled;if(boost||this._pendingFor('boost')&&this._pendingFor('boost').value!=='off')control.disabled=this._config.demo||keys.some(k=>!this._ready(k));}
    }
    for(const el of this.shadowRoot.querySelectorAll('.pending'))el.classList.remove('pending');
    for(const el of this.shadowRoot.querySelectorAll('[aria-busy]'))el.removeAttribute('aria-busy');
    for(const pending of pendings){
      const {key,value}=pending;
      const selector=key==='mode'?'#mode-select':key==='gear'?`[data-gear="${value}"]`:key==='boost'?(['off','unlimited'].includes(value)?'#boost-control':`[data-minutes="${value}"]`):key==='filter'?'#filter-reset':key==='power'?'#power-control':`[data-choice="${key}"][data-value="${value}"]`;
      const el=this.shadowRoot.querySelector(selector);
      if(el){el.classList.add('pending');el.setAttribute('aria-busy','true');}
    }
    this._text('action-status','');
    const progress=this._number('parameter_scan_progress');
    this._text('footer-status',this._config.demo?'Symulacja · bez połączenia z centralą':online&&progress!==null&&progress<100?`Odczyt nastaw · ${progress}%`:online?'Dane AERO 4 · szczegóły po kliknięciu':'Oczekiwanie na aktualne dane');
    this._applyVisibility();
  }
}
export class Aero4CardEditor extends HTMLElement {
  constructor(){super();this.attachShadow({mode:'open'});}
  setConfig(config){validateVisibility(config.visibility);this._config={...config,visibility:{...config.visibility}};this._render();}
  set hass(value){const before=this._pl;this._hass=value;if(before!==this._pl)this._render();}
  get _pl(){return String(this._hass?.locale?.language??this._hass?.language??'en').toLowerCase().startsWith('pl');}
  _emit(){this.dispatchEvent(new CustomEvent('config-changed',{detail:{config:{...this._config,visibility:{...this._config.visibility}}},bubbles:true,composed:true}));}
  _render(){
    if(!this._config)return;
    this.shadowRoot.innerHTML=`<style>:host{display:block;color:var(--primary-text-color);font:inherit}label{display:flex;gap:12px;align-items:center;padding:10px 0;cursor:pointer}input[type=checkbox]{width:20px;height:20px;accent-color:var(--primary-color)}.title{display:grid}input[type=text]{font:inherit;padding:10px;color:inherit;background:var(--card-background-color);border:1px solid var(--divider-color);border-radius:6px}fieldset{border:0;padding:0;margin:16px 0}legend{font-weight:600}p{color:var(--secondary-text-color);font-size:13px}</style><label class="title">${this._pl?'Tytuł':'Title'}<input id="title" type="text"></label><fieldset><legend>${this._pl?'Elementy widoczne na karcie':'Elements shown on the card'}</legend>${DISPLAY.map(([key,pl,en])=>`<label><input type="checkbox" data-key="${key}">${this._pl?pl:en}</label>`).join('')}</fieldset><p>${this._pl?'Czujniki jakości powietrza pojawiają się tylko wtedy, gdy mają dostępne dane. Wygląd jest automatycznie dopasowany do motywu Home Assistant.':'Air quality sensors appear only when data is available. Appearance automatically follows the Home Assistant theme.'}</p>`;
    const title=this.shadowRoot.getElementById('title');title.value=this._config.title??'';
    title.oninput=()=>{this._config={...this._config,title:title.value};this._emit();};
    for(const input of this.shadowRoot.querySelectorAll('[data-key]')){
      input.checked=this._config.visibility[input.dataset.key]!==false;
      input.onchange=()=>{this._config={...this._config,visibility:{...this._config.visibility,[input.dataset.key]:input.checked}};this._emit();};
    }
  }
}
if(!customElements.get('aero4-card-editor'))customElements.define('aero4-card-editor',Aero4CardEditor);
if(!customElements.get('aero4-card')) customElements.define('aero4-card',Aero4Card);
window.customCards=window.customCards||[];
if(!window.customCards.some(c=>c.type==='aero4-card')) window.customCards.push({type:'aero4-card',name:'AERO C14',description:'Schemat wymiennika i lokalne dane rekuperatora',preview:true});

