// Independent ARM byte/readback contract. Never trust the builder patch list.
import {borderPatches} from './gr3-border.mjs';
export const hdfSources=['native/gr3/m10v_digital_hdf.c','scripts/build_gr3_digital_hdf.py','native/gr3/m10v_hdf_menu.c','scripts/build_gr3_hdf_menu.py','native/gr3/m10v_hdf_state.h','native/gr3/m10v_hdf_adj.c','native/gr3/m10v_hdf_adj.rgba','scripts/build_gr3_hdf_adj.py'];
const need=(v,m)=>{if(!v)throw Error('digital HDF: '+m);};
const branch=(a,b,link=false)=>{const d=b-a-8;need(Number.isInteger(b)&&d%4===0&&d>=-(2**25)&&d<2**25,'branch range');return((link?0xeb000000:0xea000000)|((d>>2)&0xffffff))>>>0;};
const mov=(r,v,top=false)=>((top?0xe3400000:0xe3000000)|((v&0xf000)<<4)|(r<<12)|(v&0xfff))>>>0;
const save=[0xe92d5fff,0xe10f0000,0xe92d0003],restore=[0xe8bd0003,0xe12cf000,0xe8bd5fff];
export function hdfPatches(runtime,m){
 const h=m.digital_hdf;
 const pure=m.pure_isp_effects?.enabled===true;
 if(!h){
  need(m.hdf_enabled===false&&m.hdf_default===0,'missing native HDF owner');
  if(m.hdf_menu)need(m.border?.enabled===true&&borderPatches(runtime,m).length===20,'missing native HDF owner');
  return [];
 }
 const shared=!!m.capture_lifecycle;
 if(m.hdf_menu)need(h.ui_cache===true&&h.producer_filesystem_calls===0,'capture must use UI-published HDF cache');
 need((!shared||h.shared_recipe===true&&h.shared_offset===0x5134&&m.capture_lifecycle.snapshot?.shared_hdf===true)&&h.schema==='m10v-gr3-digital-hdf/v1'&&h.recipe_bytes===0x4778&&h.recipe_extra_bytes===(shared?0:16)&&h.isp_filesystem_calls===0&&h.pixel_loops===0&&h.mutable_global_bytes===0&&h.independent_dma===false,'owner/performance contract differs');
 const inside=(a,n=4)=>Number.isInteger(a)&&a%4===0&&a>=m.base&&a+n<=m.base+runtime.length;
 need(inside(h.base,h.bytes)&&h.bytes<=(pure?2048:1024)&&h.patches?.length===(shared?3:8),'hook extent/inventory differs');
 need(pure?!!h.optional_blur:!h.optional_blur,'optional blur mode differs');
 for(const name of (shared?['producer','gate','settings']:['alloc','producer','gate','settings']))need(inside(m.symbols['m10v_hdf_'+name])&&h.helpers?.['m10v_hdf_'+name]===m.symbols['m10v_hdf_'+name],'helper outside runtime');
 const sym=name=>m.symbols['m10v_hdf_'+name];
 const check=(at,template)=>{need(inside(at,template.length*4),'shim bounds');template.forEach((word,i)=>{if(Array.isArray(word))word=branch(at+i*4,word[0],word[1]);need(runtime.readUInt32LE(at-m.base+i*4)===(word>>>0),'instruction differs at '+(at+i*4).toString(16));});};
 const result=[];
 function shim(site,expected,name,words,link=false){const at=h.entries[name];check(at,words);result.push({address:site,expected,replacement:branch(site,at,link),name:'digital HDF '+name});}
 if(!shared)shim(0x53523e0c,0xebffb2c2,'factory',[[sym('alloc'),false]],true);
 for(const site of (shared?[]:[0x5351aed4,0x5351b068]))shim(site,0xe59420f0,'producer_0x'+site.toString(16),[...save,0xe59400f0,[sym('producer'),true],...restore,0xe59420f0,[site+4,false]]);
 shim(0x5351084c,0xeb000b2a,'request',[0xe92d41f0,0xe1a05000,0xe1a06001,[0x535134fc,true],...save,0xe1a00004,0xe1a01005,0xe1a02006,[sym('gate'),true],...restore,0xe8bd81f0],true);
 for(const [site,reg] of (shared?[]:[[0x535033d8,12],[0x53503aa0,4]]))shim(site,site===0x535033d8?0xebffff1b:0xebfffd69,'settings_0x'+site.toString(16),[0xe92d4070,0xe1a05000,0xe1a06000|reg,[0x5350304c,true],...save,0xe1a00006,0xe1a01005,[sym('settings'),true],0xe3500001,0x059d0008,0x03800001,0x058d0008,...restore,0xe8bd8070],true);
 result.push({address:0x5367c1b0,expected:0xe3580008,replacement:pure?0xe358002f:0xe358000b,name:'digital HDF clarity bound'});
 const row=h.rows-48;
 check(row,[0xe92d1001,0xe10fc000,0xe3580008,0x90281893,0x9a000003,0xe2488009,mov(0,h.rows&65535),mov(0,h.rows>>>16,true),0xe0280893,0xe12cf00c,0xe8bd1001,[0x5367c7e8,false]]);
 const rows=[[820,740,700,700,740,840,940,1024,1024,1024,1024],[680,560,500,500,540,680,860,960,1024,1024,1024],[540,400,330,330,380,540,760,920,1024,1024,1024]];
 need(inside(h.rows,66),'coefficient bounds');rows.flat().forEach((n,i)=>need(runtime.readInt16LE(h.rows-m.base+i*2)===n,'coefficient differs'));
 if(pure){
  const blur=h.optional_blur;
  need(JSON.stringify(blur.native_parameter_range)==='[8,43]'&&blur.hardware_appearance_pending===true&&blur.rows?.length===36&&inside(h.rows,39*22),'blur inventory/evidence differs');
  for(let grade=0;grade<4;grade++)for(let strength=1;strength<=3;strength++)for(let range=0;range<3;range++){
   const value=8+grade*9+(strength-1)*3+range,index=value-8;
   const core=[.18,.30,.46][strength-1],scatter=[1.5,3,6][range],weight=[.18,.32,.48][strength-1];
   const identity=blur.rows[index],base=grade?rows[grade-1]:Array(11).fill(1024);
   need(identity.native_value===value&&identity.native_r8===value+4&&identity.table_index===value-5&&identity.core_sigma===core&&identity.scatter_sigma===scatter&&identity.scatter_weight===weight,'blur row identity differs');
   for(let band=0;band<11;band++){
    const f2=(.5/2**band)**2;
    const attenuation=band>=9?1024:Math.max(0,Math.min(1024,Math.round(1024*((1-weight)*Math.exp(-2*Math.PI**2*core**2*f2)+weight*Math.exp(-2*Math.PI**2*scatter**2*f2)))));
    const gain=Math.floor((base[band]*attenuation+512)/1024);
    need(runtime.readInt16LE(h.rows-m.base+(3+index)*22+band*2)===gain&&identity.gains_q10[band]===gain&&identity.attenuation_q10[band]===attenuation,'blur coefficient differs');
   }
  }
 }
 result.push({address:0x5367c7e4,expected:0xe0281893,replacement:branch(0x5367c7e4,row),name:'digital HDF clarity row'});
 result.forEach((p,i)=>need(h.patches[i]?.address===p.address&&h.patches[i]?.expected===p.expected&&h.patches[i]?.replacement===p.replacement,'patch inventory differs'));
 return result;
}

export function hdfMenuPatches(runtime,m){
 const d=m.hdf_menu;if(!d)return [];
 const pure=m.pure_isp_effects?.enabled===true;
 const full=m.film_library_enabled!==false,offset=full?(m.capture_lifecycle?.snapshot?.snapshot_ingress_installed?0x613c:0x213c):0x13bc;
 need(d.schema==='m10v-gr3-hdf-menu/v1'&&d.film_library===full&&d.owner_offset===offset&&d.owner_bytes===offset+(pure?0x22c:0x1c0)&&d.controller_bytes===(pure?0x200:0x1c0)&&d.route===0x0200f102&&typeof m.zoom?.enabled==='boolean'&&d.rows.length===(full?3:1),'independent menu ownership differs');
 if(pure)need(JSON.stringify(d.effects_children)==='["HDF","Border","Light leak","Grain","Blur"]','pure ISP effects menu inventory differs');
 if(pure)need(full&&d.effects_cache_owner_offset===offset+0x200&&d.effects_cache_bytes===44,'effects cache ownership differs');
 const s=m.symbols,base=m.base;
 const words=(at,list)=>{need(Number.isInteger(at)&&at%4===0&&at>=base&&at+list.length*4<=base+runtime.length,'menu code bounds');list.forEach((v,i)=>need(runtime.readUInt32LE(at-base+i*4)===(v>>>0),'menu instruction differs'));};
 const vt=[0x5316c7e0,0x5316c774,0x5316c7bc,0x5316c740,0x5316c748,0x5316dfa8,0x5316c74c,0x5316c750,0x5316c754,0x5316c758,0x5316c760,0x5316c768,0x5316d0f0,0x5316c76c,0x5316cec8];
 for(const [i,n] of [[1,'destroy'],[2,'destroy'],[7,'enter'],[9,'ready'],[10,'key']]){need(Number.isInteger(s['m10v_hdf_menu_'+n]),'menu callback missing');vt[i]=s['m10v_hdf_menu_'+n];}words(d.vtable,vt);
 words(d.exports.m10v_hdf_menu_vtable,[mov(0,d.vtable&65535),mov(0,d.vtable>>>16,true),0xe12fff1e]);
 for(const [name,want] of Object.entries(full?{ctor:s.m10v_settings_controller_top_ctor,dtor:s.m10v_settings_controller_top_dtor,factory:s.m10v_settings_controller_factory,key_route:s.m10v_settings_controller_key_route}:{ctor:0x5319aa68,dtor:m.settings_menu.exports.m10v_settings_top_dtor_original,factory:m.settings_menu.exports.m10v_settings_factory_original,key_route:0x53228c4c}))need(d.exports['m10v_hdf_menu_parent_'+name]===want,'menu parent differs');
 const out=[];
 for(const [a,e,n,l] of [[0x5316f3b8,0xe300313b,'factory',false],[0x5319667c,0xe1a0c00d,'top_dtor',false],[0x5316fcf8,0xeb00ab5a,'top_ctor',true],[0x53221a4c,0xeb001c7e,'key_route',true]])out.push({address:a,expected:e,replacement:branch(a,s['m10v_hdf_menu_'+n],l),name:'HDF independent menu '+n});
 out.push({address:0x5316fcec,expected:0xe30103bc,replacement:mov(0,d.owner_bytes),name:'HDF menu owner'},{address:0x53b36adc,expected:0x1e1d1b19,replacement:((30+d.rows.length)<<24)|0x1d1b19,name:'HDF menu row count'});
 d.rows.forEach((at,i)=>{const caption=i===d.rows.length-1?(full?1140:970):[937,938,990,1024][i];words(at,[0xe92d4010,0xe1a04001,0xe1a00004,0xe3a01000,branch(at+16,0x5339de20,true),0xe1a00004,mov(1,caption),0xe1a02001,0xe8bd4010,branch(at+36,0x5339dc70)]);out.push({address:0x53b36bd0+i*8,expected:0,replacement:at,name:'HDF menu row'},{address:0x53b36c88+i*4,expected:0x10000000,replacement:full?[0x0200f100,0x0200f101,0x0200f102][i]:0x0200f102,name:'HDF menu route'});});
 if(full&&m.zoom.enabled)out.push({address:0x53b37018,expected:0x02000074,replacement:0x0200f105,name:'Crop selection and focal editor entry'});
 need(m.resources.texts[184]==='HDF 模拟'&&m.resources.texts[191]==='','independent menu captions differ');
 out.forEach((p,i)=>need(d.patches[i]?.address===p.address&&d.patches[i]?.expected===p.expected&&d.patches[i]?.replacement===p.replacement,'independent menu patch list differs'));
 return out;
}
