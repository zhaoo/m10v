// One product contract for GR III / IIIx; only camera/lens adapters differ.
const shared=Object.freeze({filmSlots:10,nativeIsp:true,liveColor:true,nativeGrain:true,digitalHdf:true,halation:true,customZoom:true,powerImages:true,ispEffects:true});
const lenses=Object.freeze({gr3:Object.freeze({base:28,min:28,max:50,defaults:Object.freeze([35,50])}),gr3x:Object.freeze({base:40,min:40,max:71,defaults:Object.freeze([50,71])})});
export const isGr3Family=model=>Object.hasOwn(lenses,model);
// New fitted films are admitted only on the shared GR III / IIIx native ISP.
export const requiresNativeIspFilm=id=>Number.isInteger(id)&&id>=328&&id<=330;
export const isLeicaFilm=id=>Number.isInteger(id)&&id>=331&&id<=334;
export const supportsNativeFilm=(model,id)=>requiresNativeIspFilm(id)?isGr3Family(model):id===327?isGr3Family(model):!(isLeicaFilm(id)||(Number.isInteger(id)&&id>=318&&id<=321))||model==='gr3';
export function modelCapabilities(model){return isGr3Family(model)?{...shared,gremote:model==='gr3',zoom:lenses[model]}:{filmSlots:5,nativeIsp:false,liveColor:false,nativeGrain:false,digitalHdf:false,halation:false,customZoom:false,powerImages:false,ispEffects:false,gremote:false,zoom:null};}
