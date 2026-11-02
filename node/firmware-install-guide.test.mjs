import test from 'node:test';
import assert from 'node:assert/strict';
import {checkCameraForInstall} from '../web/gr3/firmware-install-guide.mjs';

const gr3={model:'GR III',public_version:'2.10',sha256:'d6a3c9c288d784080e7b283222ecdd8752adfeed6faa36dab44f73115354bfd4'};
const gr3x={model:'GR IIIx',public_version:'1.60',sha256:'708e79f3b7b96a7e1581b4acf4c412233050a1832718ef7f06c8397db1b431c7'};
test('camera confirmation admits only the matching known stable camera line and pinned source',()=>{
 assert.equal(checkCameraForInstall(gr3,{model:'gr3',version:'2.10'}).ready,true);
 assert.equal(checkCameraForInstall(gr3x,{model:'gr3x',version:'1.60'}).ready,true);
 for(const [source,current] of [[gr3,{model:'gr3',version:'2.20'}],[gr3x,{model:'gr3x',version:'1.70'}],
  [gr3,{model:'gr3x',version:'2.10'}],[gr3,{model:'gr3',version:'1.60'}],[gr3,{model:'gr3',version:''}],
  [{...gr3,public_version:'2.20'},{model:'gr3',version:'2.10'}],
  [{...gr3,sha256:'f'.repeat(64)},{model:'gr3',version:'2.10'}]]){
  const result=checkCameraForInstall(source,current);assert.equal(result.ready,false);assert.ok(result.message);
 }
});
