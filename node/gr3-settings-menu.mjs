import {companionOwnerBytes} from './gr3-companion-owner.mjs';
import {zoomSources} from './gr3-zoom.mjs';
// Independent readback contract for the two owned settings controllers.
export const settingsSources=[...zoomSources,'native/gr3/m10v_film_card.c','native/gr3/m10v_film_card.h','native/gr3/m10v_film_card_data.h','native/gr3/m10v_film_font_raster.json','native/gr3/m10v_card_captions.json','scripts/generate_m10v_card_captions.py','third_party/noto-cjk/OFL.txt','native/gr3/m10v_custom_icon.rgba','scripts/generate_m10v_film_cards.py','third_party/noto-sans/NotoSans-Bold.ttf','third_party/noto-sans/OFL.txt','native/gr3/m10v_settings.c','native/gr3/m10v_settings.h','native/gr3/m10v_settings_view.c','native/gr3/m10v_settings_view.h','native/gr3/m10v_settings_controller.c','native/gr3/m10v_settings_controller.h','native/gr3/m10v_ab.h','native/gr3/m10v_ab_camera.inc','native/gr3/m10v_ab_host.inc','scripts/build_gr3_settings_hooks.py'];
const need=(c,m)=>{if(!c)throw Error('independent settings: '+m);};
const movw=(r,v)=>(0xe3000000|((v&0xf000)<<4)|(r<<12)|(v&0xfff))>>>0;
const movt=(r,v)=>(movw(r,v)|0x00400000)>>>0;
const branch=(a,b,link=false)=>{const d=b-a-8;need(Number.isInteger(b)&&d%4===0&&d>=-(2**25)&&d<2**25,'branch range');return((link?0xeb000000:0xea000000)|((d>>2)&0xffffff))>>>0;};
const stockVtable=[0x5316c7e0,0x5316c774,0x5316c7bc,0x5316c740,0x5316c748,0x5316dfa8,0x5316c74c,0x5316c750,0x5316c754,0x5316c758,0x5316c760,0x5316c768,0x5316d0f0,0x5316c76c,0x5316cec8];
export function settingsOwnerBytes(m,fallback){
 const parent=companionOwnerBytes(m,fallback);
 if(!m.adj_extra&&!m.camera_guides)return parent;
 need(m.adj_extra?.owner_offset===0x6500&&m.adj_extra?.owner_bytes===0x100&&
  m.camera_guides&&m.pure_isp_effects?.enabled===true&&m.sd_library&&m.appended_slots&&parent<=0x6500,
  'camera controls owner regions differ');
 return 0x6d00;
}
export function adjExtraPatches(runtime,m){
 const d=m.adj_extra;
 if(!d)return [];
 const inCode=at=>Number.isInteger(at)&&at%4===0&&at>=m.base&&at+8<=m.base+runtime.length;
 const original=m.symbols.m10v_adj_extra_camera_stock_slot_type;
 need(d.route===0x0200f107&&inCode(original),'ADJ route or API differs');
 need(runtime.readUInt32LE(original-m.base)===0xe1a0c00d&&
  runtime.readUInt32LE(original-m.base+4)===branch(original+4,0x531a2824),'ADJ stock trampoline differs');
 const remember=m.symbols.m10v_adj_extra_camera_remember_slot,focus=m.symbols.m10v_adj_extra_camera_virtual_focus;
 need(inCode(remember)&&inCode(focus)&&remember+40<=m.base+runtime.length,'ADJ cursor gate bounds differ');
 const guard=[0xe92d4010,0xe1a00004,branch(remember+8,focus,true),0xe8bd4010,0xe3500000,
  0x0a000001,0xe24bd014,0xe89da830,branch(remember+32,0x5320ad88,true),branch(remember+36,0x531a3164)];
 need(guard.every((word,i)=>runtime.readUInt32LE(remember-m.base+i*4)===word),'ADJ cursor gate differs');
 const hooks=[[0x531a2820,0xe1a0c00d,'slot_type',false],[0x531a45d0,0xebfffee4,'initial_render',true],
  [0x531a3160,0xeb019f08,'remember_slot',false],
  ...Array.from({length:5},(_,i)=>[0x531a48f0+0x14*i,0xe5d031f4,'touch'+i,false]),[0x53b394f4,0x5316dfa8,'enter',null]];
 if(m.debug_log?.adj_exit_trace===true)hooks.push(
  [0x531a45d8,0xebfff4bf,'trace_keys',true],[0x531a45e0,0xebfff4e2,'trace_aux_key',true],
  [0x531a45e8,0xebfff8d1,'trace_touch',true],[0x531a45f8,0xebff2355,'trace_canvas',true],
  [0x531a4610,0xeafff4a0,'trace_timer',false],[0x5316d434,0xeb0318a2,'trace_area',true],
  [0x5316d460,0xe12fff33,'trace_rect',true],[0x5316d484,0xe12fff33,'trace_layout',true],
  [0x5316d494,0xe12fff33,'trace_children',true],[0x5316d49c,0xeb08ff99,'trace_invalidate',true],
  [0x5316d4b8,0xeb152051,'trace_finish',true],
  [0x5316d4e0,0xeb0318e3,'trace_primary',true],[0x5316d558,0xeb0318d7,'trace_fallback',true],
  [0x531a4124,0xebffffcc,'trace_list',true],[0x531a413c,0xeb082109,'trace_frame',true],
  [0x531a4144,0xebfffb97,'trace_selection',true],[0x531a414c,0xebfffaa4,'trace_title',true],
  [0x531a4154,0xebfffab3,'trace_detail',true],[0x531a4164,0xeafffae1,'trace_footer',false]);
 need(d.patches?.length===hooks.length,'ADJ patch count differs');
 return hooks.map(([address,expected,name,link],i)=>{
  const entry=m.symbols['m10v_adj_extra_camera_'+name];
  need(inCode(entry),'ADJ entry outside runtime');
  const replacement=link===null?entry:branch(address,entry,link),p=d.patches[i];
  need(p.address===address&&p.expected===expected&&p.replacement===replacement,'ADJ patch contract differs');
  return {address,expected,replacement,name:'ADJ extra '+name};
 });
}
export function settingsPatches(m){
 if(!m.sd_library)return [];
 need(typeof m.zoom?.enabled==='boolean','explicit zoom enabled contract');
 const zoom=m.zoom.enabled,count=2;
 const d=m.settings_menu,s=m.symbols,ownerBytes=settingsOwnerBytes(m,m.capture_lifecycle?.snapshot?.snapshot_ingress_installed?0x613c:0x213c);
 need(d&&d.owner_bytes===ownerBytes&&JSON.stringify(d.private_routes)===JSON.stringify([33616128,33616129,33616131,33616132,...(zoom?[33616133]:[])])&&d.rows?.length===count,'missing route/owner contract');
 const patches=[];
 for(const [a,e,n,l] of [[0x5316f3b8,0xe300313b,'factory',false],[0x5319667c,0xe1a0c00d,'top_dtor',false],[0x5316fcf8,0xeb00ab5a,'top_ctor',true],[0x53221a4c,0xeb001c7e,'key_route',true]])patches.push({address:a,expected:e,replacement:branch(a,s['m10v_settings_controller_'+n],l),name:'settings '+n});
 patches.push({address:0x5316fcec,expected:0xe30103bc,replacement:movw(0,ownerBytes),name:'TopMenu owned tail'}, {address:0x53b36adc,expected:0x1e1d1b19,replacement:((30+count)<<24)|0x1d1b19,name:'Setup appended count'});
 for(let i=0;i<count;i++)patches.push({address:0x53b36bd0+i*8,expected:0,replacement:d.rows[i],name:'settings row '+i},{address:0x53b36c88+i*4,expected:0x10000000,replacement:[0x0200f100,0x0200f101,0x0200f103,0x0200f105][i],name:'settings route '+i});
 if(zoom)patches.push({address:0x53b37018,expected:0x02000074,replacement:0x0200f105,name:'Crop selection and focal editor entry'});
 return patches;
}
export function checkSettings(runtime,m){
 if(!m.sd_library){need(m.settings_menu===null,'unexpected menu');return;}
 settingsPatches(m);
 const d=m.settings_menu,s=m.symbols,base=m.base;
 const words=(a,list)=>{need(Number.isInteger(a)&&a%4===0&&a>=base&&a+list.length*4<=base+runtime.length,'code bounds');for(let i=0;i<list.length;i++)need(runtime.readUInt32LE(a-base+i*4)===(list[i]>>>0),'instruction at '+(a+i*4).toString(16));};
 if(typeof m.ab_enabled==='boolean')words(s.m10v_settings_controller_ab_available,[0xe3a00000|Number(m.ab_enabled),0xe12fff1e]);
 for(const [name,old,target] of [['m10v_settings_factory_original',0xe300313b,0x5316f3b8],['m10v_settings_top_dtor_original',0xe1a0c00d,0x5319667c]]){const a=d.exports[name];words(a,[old,branch(a+4,target+4)]);}
 const vt=[...stockVtable];for(const [i,n] of [[1,'destroy'],[2,'destroy'],[7,'enter'],[9,'ready'],[10,'key'],[12,'ab_render']])vt[i]=s['m10v_settings_controller_'+n];words(d.vtable,vt);
 words(d.exports.m10v_settings_controller_vtable,[movw(0,d.vtable&65535),movt(0,d.vtable>>>16),0xe12fff1e]);
 for(const [name,target] of [['selector',0x53221a1c],['mapper',0x5320c844],['live_enter',0x5317696c],['live_leave',0x53176de4],['live_destroy',0x53170b50],['live_event',0x531771c0],['adj_event',0x531a4db8],['adj_refresh',0x531a4114],['adj_exit',0x531a3e88],['adj_destroy',0x5319ff24],['adj_changed',0x531a4cfc],['dispatch',0x5316d5dc]]){const at=d.exports['m10v_ab_'+name+'_original'];words(at,[name==='adj_event'?0xe1d130b0:name==='adj_exit'?0xe5d02270:0xe1a0c00d,branch(at+4,target+4)]);}
 abPatches(m);
 for(let i=0;i<d.rows.length;i++){const a=d.rows[i];words(a,[0xe92d4010,0xe1a04001,0xe1a00004,0xe3a01000,branch(a+16,0x5339de20,true),0xe1a00004,movw(1,[937,938,990,1024][i]),0xe1a02001,0xe8bd4010,branch(a+36,0x5339dc70)]);}
 need(m.resources.texts[151]==='胶卷库'&&m.resources.texts[152]==='水印','root captions');
 need(JSON.stringify(m.resources.texts.slice(179,184))===JSON.stringify(['编辑：水印模式','编辑：日期格式','编辑：显示位置','编辑：文字颜色','选择胶卷']),'focus captions');
}

export function abPatches(m){
 if(!m.sd_library||m.film_library_enabled===false)return [];
 const d=m.settings_menu,s=m.symbols;
 const sites=[['selector',0x53221a1c],['mapper',0x5320c844],['live_enter',0x5317696c],['live_leave',0x53176de4],['live_destroy',0x53170b50],['live_event',0x531771c0],['adj_event',0x531a4db8],['adj_refresh',0x531a4114],['adj_exit',0x531a3e88],['adj_destroy',0x5319ff24],['adj_changed',0x531a4cfc],['dispatch',0x5316d5dc]];
 need(d?.ab_hooks?.length===12,'missing A/B hooks');
 need(d.ab_host?.stage==='compare'&&d.ab_host.route===0x02000000&&d.ab_host.menu_parent===0x02000012&&d.ab_host.custom_root===false&&d.ab_host.tone_changes===true&&d.ab_host.root_rows===0&&d.ab_host.direct_pair===true&&d.ab_host.live_ui===false&&d.ab_host.picker_page_rows===6&&d.ab_host.choices===(m.appended_slots?22:12),'native comparison host contract');
 return sites.map(([name,address],i)=>{
  const p={address,expected:name==='adj_event'?0xe1d130b0:name==='adj_exit'?0xe5d02270:0xe1a0c00d,replacement:branch(address,s['m10v_settings_controller_ab_'+name]),name:'A/B '+name};
  need(['address','expected','replacement'].every(k=>p[k]===d.ab_hooks[i][k]),'A/B hook differs');return p;
 });
}
