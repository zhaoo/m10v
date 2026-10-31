// One product contract for GR III / IIIx; only camera/lens adapters differ.
const shared=Object.freeze({filmSlots:10,nativeIsp:true,liveColor:true,nativeGrain:true,digitalHdf:true,halation:true,customZoom:true,powerImages:true,ispEffects:true});
const lenses=Object.freeze({gr3:Object.freeze({base:28,min:28,max:50,defaults:Object.freeze([35,50])}),gr3x:Object.freeze({base:40,min:40,max:71,defaults:Object.freeze([50,71])})});
export const isGr3Family=model=>Object.hasOwn(lenses,model);
// These four profiles have only been integrated with the GR III native ISP.
export const supportsNativeFilm=(model,id)=>!(Number.isInteger(id)&&id>=318&&id<=321)||model==='gr3';
export function modelCapabilities(model){return isGr3Family(model)?{...shared,zoom:lenses[model]}:{filmSlots:5,nativeIsp:false,liveColor:false,nativeGrain:false,digitalHdf:false,halation:false,customZoom:false,powerImages:false,ispEffects:false,zoom:null};}
