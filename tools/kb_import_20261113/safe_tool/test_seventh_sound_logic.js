const fs=require('fs'),vm=require('vm'),assert=require('assert');
const src=fs.readFileSync(require('path').join(__dirname,'files','backend','app','static','xz_sos_app.js'),'utf8');
const injected=src.replace(/\}\)\(\);\s*$/, `window.__test={bootstrap,logout,pushKeyMatches,onAlertsToggle,savedSoundPreference,updateRingStatus};})();`);
if(injected===src)throw Error('Cannot inject test hooks');
const elems=new Map();
function el(id){if(!elems.has(id)) elems.set(id,{id,textContent:'',value:'',checked:false,style:{},classList:{toggle(){}},children:[],addEventListener(){},before(){},replaceChildren(){},appendChild(){},setAttribute(){},scrollIntoView(){},focus(){}});return elems.get(id)}
class LocalStore { getItem(key){return this[key]??null} setItem(key,v){this[key]=String(v)} removeItem(key){delete this[key]} }
const localStorage=new LocalStore();
let currentId='userA';
const API={
 '/api/me':()=>({id:currentId,role:'supervisor',is_active:true,username:currentId,display_name:currentId,org:{name:'測試機構'}}),
 '/api/jiaan1030/emergencies?status=active':()=>({items:[]}),
 '/api/jiaan1030/emergencies?status=resolved':()=>({items:[]}),
};
const context={
 window:{addEventListener(){},AudioContext:class{constructor(){this.state='suspended';this.currentTime=0}resume(){this.state='running';return Promise.resolve()}createOscillator(){return {frequency:{value:0,setTargetAtTime(){}},connect(){},start(){}}}createWaveShaper(){return {connect(){},curve:null}}createGain(){return {gain:{value:0,setTargetAtTime(){},cancelScheduledValues(){}},connect(){}}}createDynamicsCompressor(){return {threshold:{},knee:{},ratio:{},attack:{},release:{},connect(){}}}},},
 document:{getElementById:el,addEventListener(){},title:'test',visibilityState:'visible',createElement(){return {style:{},addEventListener(){},appendChild(){},setAttribute(){}}}},
 localStorage,Notification:undefined,fetch:async url=>({ok:true,async json(){const path=String(url);if(!API[path])throw Error(`Unexpected GET: ${path}`);return API[path]()}}),
 setInterval:()=>1,clearInterval(){},setTimeout(){},console,crypto:{randomUUID(){return '11111111-1111-4111-8111-111111111111'}},confirm(){return false},prompt(){return ''},navigator:{},atob:(x)=>Buffer.from(x,'base64').toString('binary')
};context.window.document=context.document;
vm.createContext(context);vm.runInContext(injected,context);
(async()=>{
 const api=context.window.__test;
 localStorage.setItem('xz_sos_sound_enabled_v1:userA','1');
 currentId='userB';await api.bootstrap('session-B');
 assert.equal(el('alerts').checked,false,'Other account preference must not leak');
 await api.logout(false); assert.equal(el('alerts').checked,false,'Logout must reset checked state');
 currentId='userA';await api.bootstrap('session-A');
 assert.equal(el('alerts').checked,true,'Saved preference for same user must restore');
 assert.equal(api.savedSoundPreference(),true);
 // check VAPID mismatch detection without ever contacting remote push services
 const serverKey=Buffer.from([1,2,3,4,5]).toString('base64url');
 assert.equal(api.pushKeyMatches({options:{applicationServerKey:Uint8Array.from([1,2,3,4,5]).buffer}},serverKey),true);
 assert.equal(api.pushKeyMatches({options:{applicationServerKey:Uint8Array.from([1,2,3,7]).buffer}},serverKey),false);
 assert.equal(api.pushKeyMatches({options:{}},serverKey),null);
 console.log('PASS: cross-user preference, logout reset, same-user restore, VAPID match/mismatch/unknown (6 checks)');
})().catch(e=>{console.error(e);process.exitCode=1});
