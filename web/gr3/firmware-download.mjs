// Restore the ordinary binary response locally, after the complete audit record
// has crossed the network in the body instead of oversized HTTP headers.
export async function unwrapFirmwareDownload(response){
 if(!response.ok||!/^multipart\/form-data\b/i.test(response.headers.get('Content-Type')||''))return response;
 try{
  const parts=await response.formData(),firmware=parts.get('firmware');
  const metadata=JSON.parse(parts.get('metadata'));
  if(!firmware||typeof firmware.arrayBuffer!=='function'||!metadata?.headers)throw Error();
  const headers=new Headers(metadata.headers);
  if(headers.get('Content-Type')!=='application/octet-stream'||Number(headers.get('Content-Length'))!==firmware.size)throw Error();
  return new Response(firmware,{headers});
 }catch(error){if(error.name==='AbortError')throw error;throw Error('固件下载内容不完整或校验记录格式错误，请重新保存。');}
}
