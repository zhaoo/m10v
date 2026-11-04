import {readFileSync} from 'node:fs';
import {nativeCatalog} from '../node/gr3-native-library.mjs';
import {sdFilmRecord} from '../node/gr3-sd-film-pack.mjs';
import {sha256} from '../node/gr3-fit-binding.mjs';

const contract=JSON.parse(readFileSync(new URL('../contracts/companion-v1.json',import.meta.url)));
const catalog=await nativeCatalog();
// Match GRemote's sync_m10v_contract + sync_camera_contract metadata, without
// importing the phone renderer or any private pairing material.
const cameraCatalog={schemaVersion:1,rendererHash:sdFilmRecord(33).subarray(8448,8480).toString('hex'),entries:catalog.films.map(f=>({
 id:f.id,name:f.name,group:f.group,icon:`assets/films/camera-icons/${f.id}.png`,
 parameters:Object.fromEntries(Object.entries(contract.parameters).filter(([,p])=>(!p.filmIds||p.filmIds.includes(f.id))&&!p.excludeFilmIds?.includes(f.id)).map(([key,p])=>[key,{min:p.min,max:p.overrides?.[f.id]??p.max,default:p.default,label:p.label}])),
 approximation:f.approximation??false,
}))};
const gremoteCameraMetadata=Object.freeze({catalogHash:sha256(cameraCatalog),rendererHash:cameraCatalog.rendererHash});
process.stdout.write(JSON.stringify(process.argv.includes('--catalog')?{...cameraCatalog,hash:gremoteCameraMetadata.catalogHash}:gremoteCameraMetadata));
