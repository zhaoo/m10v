import {randomBytes} from 'node:crypto';

// Browsers opt in to a body-carried audit record. Legacy binary clients keep
// their existing response, while growing receipts no longer hit proxy limits.
export function sendFirmwareDownload(request,response,candidate,filename){
 const headers={'Content-Type':'application/octet-stream','Content-Length':candidate.length,
  'Content-Disposition':`attachment; filename="${filename}"`,'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'};
 if(request.headers.accept!=='multipart/form-data'){
  response.writeHead(200,headers);return response.end(candidate);
 }
 const metadata={headers:{...headers}};
 for(const name of response.getHeaderNames())if(name.startsWith('x-m10v-')){
  metadata.headers[name]=String(response.getHeader(name));response.removeHeader(name);
 }
 const boundary='m10v-'+randomBytes(24).toString('hex');
 const prefix=Buffer.from(`--${boundary}\r\nContent-Disposition: form-data; name="metadata"\r\nContent-Type: application/json\r\n\r\n${JSON.stringify(metadata)}\r\n--${boundary}\r\nContent-Disposition: form-data; name="firmware"; filename="${filename}"\r\nContent-Type: application/octet-stream\r\n\r\n`);
 const suffix=Buffer.from(`\r\n--${boundary}--\r\n`);
 response.writeHead(200,{...headers,'Content-Type':`multipart/form-data; boundary=${boundary}`,'Content-Length':prefix.length+candidate.length+suffix.length});
 response.write(prefix);response.write(candidate);response.end(suffix);
}
