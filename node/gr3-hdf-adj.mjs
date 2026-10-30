// Independent inventory and byte verifier for the added ADJ function20.
// Constants come from exact official GR III2.10 RTOS, not builder metadata.
import {createHash} from 'node:crypto';
const need=(v,m)=>{if(!v)throw Error('HDF ADJ: '+m);};
const mov=(r,v,t=false)=>((t?0xe3400000:0xe3000000)|((v&0xf000)<<4)|(r<<12)|(v&0xfff))>>>0;
const branch=(a,b)=>{const d=b-a-8;need(Number.isInteger(b)&&d%4===0&&d>=-(2**25)&&d<2**25,'branch range');return(0xea000000|((d>>2)&0xffffff))>>>0;};
const readers=[[0x5319fff8,0x531a002c,6],[0x531a1e3c,0x531a1e40,4],[0x531a2a48,0x531a2a50,2],[0x531a2ac0,0x531a2ac8,7],[0x531a2c6c,0x531a2c74,3],[0x531a3128,0x531a3130,2],[0x531a31c4,0x531a31cc,2],[0x531a3c24,0x531a3c2c,2],[0x531a3c9c,0x531a3ca4,2],[0x531a3dcc,0x531a3dd4,2],[0x531a3ee0,0x531a3ee8,2],[0x531a4080,0x531a4088,2],[0x531a4234,0x531a4238,3],[0x531a4488,0x531a4494,4],[0x531a458c,0x531a4594,2],[0x531a468c,0x531a4694,2],[0x531a46f4,0x531a4704,7],[0x531a47b0,0x531a47c0,7],[0x531a487c,0x531a4884,2]];
const lists=[0x53b4eba0,0x53b5a430,0x53b5a404,0x53b58fb0,0x53b5a4b4];
const originalList=Buffer.from([0,1,2,3,4,16,5,6,7,8,9,18,19,10,11,12,13,17,14,20]);
const tableSHA='639cda68e68cf568808d37c122d3c575c67b10da03fa60ed8cd1d7f90fe153a6';
export function hdfAdjPatches(runtime,m){
 const h=m.hdf_adj;
 if(!h){need(!m.hdf_menu||(m.border?.enabled===true&&m.hdf_enabled===false),'independent option missing');return [];}
 const inside=(a,n=4)=>Number.isInteger(a)&&a%4===0&&Number.isInteger(n)&&n>=0&&a>=m.base&&a+n<=m.base+runtime.length;
 const within=(a,n=4)=>inside(a,n)&&a>=h.base&&a+n<=h.base+h.bytes;
 need(h.schema==='m10v-gr3-hdf-adj/v1'&&h.function_id===20&&h.record_count===21&&h.record_bytes===0x44&&h.original_table===0x53b39a14&&h.original_table_bytes===0x550&&h.required_rtos_sha256==='8a4eafcad2716e0b21e9909264e1242e534f0e39e05cba82a53546ceb4070b67','identity/record contract differs');
 need(inside(h.base,h.bytes)&&within(h.table,21*0x44)&&h.icon_id===874&&h.camera_tested===false,'extent/icon/camera claim differs');
 need(createHash('sha256').update(runtime.subarray(h.table-m.base,h.table-m.base+0x550)).digest('hex')===tableSHA,'original twenty records differ');
 if(m.settings_menu)need(h.parent_event===m.symbols?.m10v_settings_controller_ab_adj_event,'parent event composition differs');
 const names=['enter','draw','current','set','count','available','event'];
 for(const n of names)need(inside(m.symbols?.['m10v_hdf_adj_'+n])&&h.handlers?.[n]===m.symbols['m10v_hdf_adj_'+n],'handler outside runtime or differs');
 // "available" is the existing export name for stock +0x3c exclusion:
 // native render/navigation consumes zero as usable, nonzero as hidden.
 const record=Array(17).fill(0);
 for(const [off,n] of [[0,'enter'],[0x18,'draw'],[0x20,'current'],[0x28,'set'],[0x30,'count'],[0x3c,'available']])record[off/4]=m.symbols['m10v_hdf_adj_'+n];
 const words=(at,values)=>{need(within(at,values.length*4),'shim bounds');values.forEach((v,i)=>need(runtime.readUInt32LE(at-m.base+i*4)===(v>>>0),'instruction differs at '+(at+i*4).toString(16)));};
 words(h.table+0x550,record);
 need(JSON.stringify(h.table_readers)===JSON.stringify(readers.map(([lo,hi])=>[lo,hi])),'reader inventory differs');
 need(h.cache?.offset===0x190&&h.cache.bytes===20&&h.cache.page_bytes===0x1c0&&h.cache.capture_filesystem_calls===0,'cache ownership differs');
 const out=[];
 const add=(address,expected,replacement)=>out.push({address,expected:expected>>>0,replacement:replacement>>>0,name:'HDF independent ADJ'});
 const pointer=(lo,hi,reg,old,address)=>{add(lo,mov(reg,old&65535),mov(reg,address&65535));add(hi,mov(reg,old>>>16,true),mov(reg,address>>>16,true));};
 const target=site=>{const p=h.patches?.find(p=>p.address===site);need(p&&Number.isInteger(p.replacement)&&(p.replacement>>>24)===0xea,'branch inventory differs');let d=(p.replacement&0xffffff)<<2;if(d&0x2000000)d-=0x4000000;const at=site+8+d;need(within(at),'branch target outside module');return at;};
 readers.forEach(([lo,hi,r])=>pointer(lo,hi,r,0x53b39a14,h.table));
 const length=target(0x531a1e54);words(length,[0xe2846e55,0xe2866044,branch(length+8,0x531a1e58)]);add(0x531a1e54,0xe2846e55,branch(0x531a1e54,length));
 need(h.lists?.length===5,'five assignment lists required');
 for(let i=0;i<5;i++){
  const row=h.lists[i];need(row.original===lists[i]&&row.count===20&&within(row.address,20)&&runtime.subarray(row.address-m.base,row.address-m.base+20).equals(originalList),'assignment order/extent differs');
  for(const [lo,hi] of [[0x531b55a4+i*0x5c,0x531b55ac+i*0x5c],[0x531b71cc+i*0x30,0x531b71d0+i*0x30],[0x531b895c+i*0x34,0x531b8960+i*0x34]])pointer(lo,hi,3,lists[i],row.address);
  add(0x531b3bac+i*8,0xe3a00013,0xe3a00014);
  const site=0x53246340+i*12,at=target(site),off=0x918+i*2;words(at,[0xe5d30000|off,0xe3500014,0x83a00000,0xe12fff1e]);add(site,0xe5d30000|off,branch(site,at));
 }
 const name=target(0x532928b0);words(name,[0xe3510014,0x030003ca,0x012fff1e,0xe3510013,0x13a00000,0x03a00049,0xe12fff1e]);add(0x532928b0,0xe3510013,branch(0x532928b0,name));
 const icon=target(0x53293ad0);words(icon,[0xe3510014,0x0300036a,0x012fff1e,0xe2410013,0xe16f0f10,0xe1a002a0,0xe12fff1e]);add(0x53293ad0,0xe2410013,branch(0x53293ad0,icon));
 add(0x531a4db8,0xe1d130b0,branch(0x531a4db8,m.symbols.m10v_hdf_adj_event));
 need(h.patches?.length===out.length,'patch count differs');
 out.forEach((p,i)=>{const q=h.patches[i];need(q.address===p.address&&q.expected===p.expected&&q.replacement===p.replacement,'patch inventory differs');});
 return out;
}
