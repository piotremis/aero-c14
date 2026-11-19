                                                                                    
const DAYS=['monday','tuesday','wednesday','thursday','friday','saturday','sunday','holiday'];
const LABELS={pl:['PN','WT','ŚR','CZ','PT','SO','ND','Święto'],en:['Mon','Tue','Wed','Thu','Fri','Sat','Sun','Holiday']};
const TEXT={
  title:['Harmonogram Nano','Nano schedule'],refresh:['Odczytaj','Refresh'],period:['Przedział','Period'],
  loading:['Odczytywanie…','Loading…'],days:['Dni','Days'],
  preview:['Podgląd przedziałów','Period preview'],draft_legend:['Linia przerywana: niezapisana edycja','Dashed outline: unsaved edit'],
  start:['Początek','Start'],end:['Koniec','End'],save:['Zapisz','Save'],disable:['Wyłącz przedział','Disable period'],
  unknown:['Brak odczytu','No reading'],disabled:['Wyłączony','Disabled'],dirty:['Niezapisane zmiany','Unsaved changes'],
  waiting:['Oczekiwanie na potwierdzenie…','Awaiting confirmation…'],saved:['Zmiana potwierdzona','Change confirmed'],
  partial:['Nie potwierdzono całej zmiany. Sprawdź odczytane granice przed ponowieniem.','The change was not fully confirmed. Check the received boundaries before retrying.'],
  invalid:['Wybierz kwadranse w obrębie jednego dnia albo 00:00 / 00:00.','Choose quarter hours within one day, or 00:00 / 00:00.'],
  load_failed:['Nie udało się odczytać harmonogramu. Sprawdź połączenie, uprawnienia i czy poprzednia operacja już się zakończyła.','Could not read the schedule. Check the connection, permissions and whether the previous operation has finished.'],
  missing:['Brak odczytu tego dnia. Poczekaj na pełny odczyt lub wybierz Odczytaj. Rozszerzone nastawy muszą być włączone.','No readings for this day. Wait for the scan or choose Read. Extended settings must be enabled.'],
  demo:['Podgląd — bez połączenia z urządzeniem','Preview — no device connection'],
  help:['Każdy przedział zapisujesz osobno. Koniec dnia: 24:00.','Save each period separately. End of day: 24:00.'],
};
const styles=`:host{display:block;font-family:var(--paper-font-body1_-_font-family,system-ui,sans-serif)}*{box-sizing:border-box}[hidden]{display:none!important}
ha-card{display:block;padding:20px;border:1px solid var(--divider-color,#ffffff15);border-radius:20px;background:var(--ha-card-background,var(--card-background-color,#111e2a));color:var(--primary-text-color,#e9f1f8)}
header{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:18px}h2{font-size:20px;font-weight:600;margin:0;letter-spacing:-.03em}button,select{font:inherit;color:inherit;background:transparent;border:1px solid var(--divider-color,#ffffff25);border-radius:9px;padding:9px 10px;min-height:40px}button{cursor:pointer}button:disabled,select:disabled{opacity:.45;cursor:default}button:focus-visible,select:focus-visible{outline:2px solid var(--primary-color,#36bdcf);outline-offset:2px}button:not(:disabled):hover{background:#36bdcf15}
.days{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:6px;margin-bottom:20px}.days button{font-size:12px;padding:8px 3px}.days button[aria-pressed=true]{background:#2dc4d522;border-color:#2dc4d580;color:var(--primary-color,#49d2df)}
fieldset{min-width:0;margin:0 0 14px;padding:14px;border:1px solid var(--divider-color,#ffffff18);border-radius:13px}legend{font-size:13px;padding:0 6px;color:var(--secondary-text-color,#9aaec0)}.times{display:grid;grid-template-columns:1fr 1fr;gap:12px}label{display:grid;gap:6px;font-size:11px;color:var(--secondary-text-color,#9aaec0)}select{width:100%;font-size:16px;font-variant-numeric:tabular-nums;color:var(--primary-text-color,#e9f1f8);background:var(--ha-card-background,var(--card-background-color,#111e2a))}.actions{display:flex;gap:8px;justify-content:space-between;align-items:center;margin-top:12px}.save{background:#2dc4d51a;border-color:#2dc4d560}.disable{font-size:11px}.status{font-size:11px;color:var(--secondary-text-color,#9aaec0);margin-top:10px;min-height:15px}.notice{font-size:12px;line-height:1.5;margin:10px 0}.notice.error{color:var(--error-color,#ff9a94)}.help{font-size:11px;color:var(--secondary-text-color,#9aaec0);line-height:1.6;margin:8px 0 0}.preview{margin:0 0 12px}.preview figcaption{font-size:11px;color:var(--secondary-text-color,#9aaec0);margin-bottom:8px}.preview svg{display:block;width:100%;height:auto}.preview text{font-family:inherit;fill:var(--secondary-text-color,#9aaec0);font-size:9px}.preview .axis{stroke:var(--divider-color,#ffffff20);stroke-width:1}.preview .period{fill:#36bdcf;stroke:#36bdcf}.preview .period[data-period="2"]{fill:#edba5e;stroke:#edba5e}.preview .period[data-period="3"]{fill:#a38ddd;stroke:#a38ddd}.preview .draft{fill-opacity:.25;stroke-dasharray:3 2;stroke-width:1.5}.preview .legend{font-size:10px;color:var(--secondary-text-color,#9aaec0);min-height:14px}@media(max-width:380px){ha-card{padding:16px}header{gap:8px}h2{font-size:18px}fieldset{padding:10px}.disable{padding:8px}.actions{gap:6px}}`;

const time=unit=>`${String(Math.floor(unit/4)).padStart(2,'0')}:${String(unit%4*15).padStart(2,'0')}`;
const units=(value,end=false)=>{
  const limit=end?96:95;
  for(let unit=0;unit<=limit;unit++)if(time(unit)===value)return unit;
  return null;
};

export class Aero4ScheduleCard extends HTMLElement {
  constructor(){
    super();this.attachShadow({mode:'open'});this._day='monday';this._draft={};this._days=null;
    this._busy=false;this._loading=false;this._requested=false;this._notice='';
    this._revision=0;
  }
  connectedCallback(){
    if(!this._timer)this._timer=setInterval(()=>{
      if(this._hass&&!this._config?.demo&&!this._busy&&!this._loading&&!Object.keys(this._draft).length)void this._load(false);
    },30000);
  }
  disconnectedCallback(){clearInterval(this._timer);this._timer=null;}
  setConfig(config){
    if(!config||config.entry_id!==undefined&&typeof config.entry_id!=='string'||config.demo!==undefined&&typeof config.demo!=='boolean')throw Error('Invalid AERO 4 schedule card configuration');
    this._revision++;this._config={...config};this._requested=false;this._days=null;this._draft={};this._notice='';this._busy=false;this._loading=false;
    if(config.demo){
      this._days=Object.fromEntries(DAYS.map(day=>[day,[1,2,3].map(period=>({period,start:time((4+period*4)*4),end:time((5+period*4)*4),status:'known'}))]));
    }
    this._render();this._startLoad();
  }
  set hass(value){this._hass=value;this._startLoad();if(this._renderedLanguage!==this._language)this._render();}
  get _language(){return String(this._hass?.locale?.language??this._hass?.language??'en').toLowerCase().startsWith('pl')?'pl':'en';}
  _t(key){return TEXT[key][this._language==='pl'?0:1];}
  getCardSize(){return 8;}
  getGridOptions(){return {columns:12,rows:8,min_columns:6,min_rows:6};}
  static getStubConfig(){return {type:'custom:aero4-schedule-card'};}
  _startLoad(){
    if(this._config&&!this._config.demo&&!this._requested&&this._hass?.callWS){
      this._requested=true;void this._load();
    }
  }
  async _service(service,data={}){
    if(this._config.demo)throw Error('Demo cannot call services');
    const result=await this._hass.callWS({type:'call_service',domain:'compit_aero4',service,
      service_data:{...(this._config.entry_id?{entry_id:this._config.entry_id}:{}),...data},return_response:true});
    return result.response;
  }
  _normalize(data){
    if(!data?.days||typeof data.days!=='object')throw Error('Missing schedule');
    return Object.fromEntries(DAYS.map(day=>[day,[1,2,3].map(period=>{
      const row=Array.isArray(data.days[day])?data.days[day].find(item=>item?.period===period):null;
      const known=row?.status==='known'&&units(row.start)!==null&&units(row.end,true)!==null;
      return {period,start:known?row.start:null,end:known?row.end:null,status:known?'known':'unavailable'};
    })]));
  }
  async _load(clearNotice=true,fresh=false){
    if(!this._config||this._config.demo)return;
    const revision=this._revision;
    this._loading=true;if(clearNotice)this._notice='';this._render();
    try{
      const data=await this._service('get_schedule',fresh?{refresh_day:this._day}:{});if(revision!==this._revision)return;
      this._days=this._normalize(data);
      for(const [key,values] of Object.entries(this._draft)){
        const [day,number]=key.split('_'),row=this._days[day]?.find(item=>item.period===Number(number));
        if(row&&row.start===values.start&&row.end===values.end)delete this._draft[key];
      }
    }catch{
      if(revision!==this._revision)return;
      this._days=null;if(this._notice!=='partial')this._notice='load_failed';
    }finally{if(revision===this._revision){this._loading=false;this._render();}}
  }
  _row(period){return this._days?.[this._day]?.find(row=>row.period===period)??{period,start:null,end:null,status:'unavailable'};}
  _values(period){const row=this._row(period);return this._draft[`${this._day}_${period}`]??{start:row.start,end:row.end};}
  _change(period,boundary,value){
    this._putDraft(period,{...this._values(period),[boundary]:value});
  }
  _putDraft(period,values){
    const row=this._row(period),key=`${this._day}_${period}`;
    if(values.start===row.start&&values.end===row.end)delete this._draft[key];else this._draft[key]=values;
    this._notice='';this._render();
  }
  _valid(values){const start=units(values.start),end=units(values.end,true);return start!==null&&end!==null&&(start<end||start===0&&end===0);}
  async _save(period){
    if(this._busy||this._loading||this._config.demo||this._row(period).status!=='known')return;
    const values=this._values(period),day=this._day,revision=this._revision;
    if(!this._valid(values)){this._notice='invalid';this._render();return;}
    this._busy=true;this._notice='waiting';this._render();
    try{
      const result=await this._service('set_schedule_period',{day,period,...values});
      if(revision!==this._revision)return;
      if(result?.status!=='succeeded')throw Error('Unconfirmed schedule');
      delete this._draft[`${day}_${period}`];this._notice='saved';await this._load(false);
    }catch{
      if(revision!==this._revision)return;
      delete this._draft[`${day}_${period}`];this._notice='partial';await this._load(false);
    }finally{if(revision===this._revision){this._busy=false;this._render();}}
  }
  _preview(){
    const figure=document.createElement('figure');figure.className='preview';
    const caption=document.createElement('figcaption');caption.textContent=this._t('preview');figure.append(caption);
    const ns='http://www.w3.org/2000/svg',svg=document.createElementNS(ns,'svg');
    svg.setAttribute('viewBox','0 0 288 102');svg.setAttribute('role','img');svg.setAttribute('aria-label',this._t('preview'));
    figure.append(svg);
    const add=(tag,attributes,text)=>{
      const node=document.createElementNS(ns,tag);for(const [key,value] of Object.entries(attributes))node.setAttribute(key,String(value));
      if(text!==undefined)node.textContent=text;svg.append(node);return node;
    };
    for(let hour=0;hour<=24;hour+=6){
      const x=24+hour/24*252;
      add('line',{x1:x,x2:x,y1:19,y2:91,class:'axis'});
      add('text',{x,y:11,'text-anchor':hour===24?'end':hour===0?'start':'middle'},`${hour}:00`);
    }
    let editing=false;
    for(let period=1;period<=3;period++){
      const row=this._row(period),values=this._values(period),y=30+(period-1)*24;
      const first=units(values.start),last=units(values.end,true);
      const dirty=values.start!==row.start||values.end!==row.end;editing||=dirty;
      add('text',{x:7,y:y+3},String(period));
      add('line',{x1:24,x2:276,y1:y,y2:y,class:'axis','stroke-dasharray':row.status==='known'?'none':'3 3'});
      if(first!==null&&last!==null&&first<last){
        const rect=add('rect',{x:24+first/96*252,y:y-5,width:(last-first)/96*252,height:10,rx:3,
          class:`period${dirty?' draft':''}`,'data-period':period});
        const title=document.createElementNS(ns,'title');title.textContent=`${this._t('period')} ${period}: ${values.start} – ${values.end}`;rect.append(title);
      }
    }
    const legend=document.createElement('div');legend.className='legend';legend.textContent=editing?this._t('draft_legend'):'';figure.append(legend);
    return figure;
  }
  _render(){
    if(!this._config)return;
    this._renderedLanguage=this._language;
    const locked=this._busy||this._loading;
    this.shadowRoot.innerHTML=`<style>${styles}</style><ha-card><header><h2></h2><button id="refresh" type="button"></button></header><nav class="days" aria-label="Days"></nav><div id="periods"></div><div class="notice" role="status" aria-live="polite"></div><p class="help"></p></ha-card>`;
    this.shadowRoot.querySelector('h2').textContent=this._config.title??this._t('title');
    const refresh=this.shadowRoot.getElementById('refresh');refresh.textContent=this._t('refresh');refresh.disabled=locked||!!this._config.demo;refresh.onclick=()=>void this._load(true,true);
    const navigation=this.shadowRoot.querySelector('nav');
    navigation.setAttribute('aria-label',this._t('days'));
    DAYS.forEach((day,index)=>{
      const button=document.createElement('button');button.type='button';button.textContent=LABELS[this._language][index];
      button.dataset.day=day;button.setAttribute('aria-pressed',String(day===this._day));button.disabled=locked;
      button.onclick=()=>{this._day=day;this._notice='';this._render();};navigation.append(button);
    });
    const periods=this.shadowRoot.getElementById('periods');
    periods.before(this._preview());
    for(let period=1;period<=3;period++){
      const row=this._row(period),values=this._values(period),known=row.status==='known';
      const fieldset=document.createElement('fieldset');fieldset.dataset.period=period;
      const legend=document.createElement('legend');legend.textContent=`${this._t('period')} ${period}`;fieldset.append(legend);
      const times=document.createElement('div');times.className='times';fieldset.append(times);
      for(const boundary of ['start','end']){
        const label=document.createElement('label');label.append(document.createTextNode(this._t(boundary)));
        const select=document.createElement('select');select.dataset.boundary=boundary;select.disabled=locked||!known;
        if(!known){const option=document.createElement('option');option.value='';option.textContent='—';select.append(option);}
        for(let unit=0;unit<=(boundary==='end'?96:95);unit++){
          const option=document.createElement('option');option.value=option.textContent=time(unit);select.append(option);
        }
        select.value=values[boundary]??'';select.onchange=()=>this._change(period,boundary,select.value);label.append(select);times.append(label);
      }
      const actions=document.createElement('div');actions.className='actions';fieldset.append(actions);
      const disable=document.createElement('button');disable.type='button';disable.className='disable';disable.textContent=this._t('disable');disable.disabled=locked||!known;
      disable.onclick=()=>this._putDraft(period,{start:'00:00',end:'00:00'});actions.append(disable);
      const save=document.createElement('button');save.type='button';save.className='save';save.textContent=this._t('save');
      const dirty=values.start!==row.start||values.end!==row.end;
      save.disabled=locked||!known||!dirty||!this._valid(values)||!!this._config.demo;save.onclick=()=>void this._save(period);actions.append(save);
      const status=document.createElement('div');status.className='status';status.textContent=!known?this._t('unknown'):dirty&&!this._valid(values)?this._t('invalid'):dirty?this._t('dirty'):row.start===row.end&&row.start==='00:00'?this._t('disabled'):'';fieldset.append(status);
      periods.append(fieldset);
    }
    const anyKnown=DAYS.some(day=>this._days?.[day]?.some(row=>row.status==='known'));
    const notice=this.shadowRoot.querySelector('.notice');notice.textContent=this._config.demo?this._t('demo'):this._notice?this._t(this._notice):this._loading?this._t('loading'):!anyKnown?this._t('missing'):'';
    notice.classList.toggle('error',['partial','invalid','load_failed'].includes(this._notice));
    this.shadowRoot.querySelector('.help').textContent=this._t('help');
  }
}
if(!customElements.get('aero4-schedule-card'))customElements.define('aero4-schedule-card',Aero4ScheduleCard);
window.customCards=window.customCards||[];
if(!window.customCards.some(card=>card.type==='aero4-schedule-card'))window.customCards.push({type:'aero4-schedule-card',name:'AERO C14 schedule',description:'Native eight-day Nano schedule',preview:true});
