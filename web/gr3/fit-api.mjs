import {unwrapFirmwareDownload} from './firmware-download.mjs';

export function createFitApi(getToken,fetcher=globalThis.fetch){
 return async(path,options={})=>{
  const response=await fetcher(path,{...options,headers:{'X-M10V-Token':getToken(),
   ...(path.endsWith('/edit/build')?{Accept:'multipart/form-data'}:{}),...options.headers}});
  if(!response.ok){
   let message=`请求失败（HTTP ${response.status}）`;
   try{message=(await response.json()).error||message;}catch{}
   throw Error(message);
  }
  return unwrapFirmwareDownload(response);
 };
}
