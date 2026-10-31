import test from 'node:test';
import assert from 'node:assert/strict';
import {createServer} from './server.mjs';
import {renderNavigation} from '../web/shared/navigation.js';
test('retired test-package page is unavailable and absent from navigation',async()=>{
 const server=createServer();await new Promise(r=>server.listen(0,'127.0.0.1',r));
 try{
  for(const route of ['/test-packages','/test-packages/','/test-packages.html'])assert.equal((await fetch(`http://127.0.0.1:${server.address().port}${route}`)).status,404);
  assert.ok(!renderNavigation('/').includes('test-packages'));
 }finally{await new Promise(r=>server.close(r));}
});
