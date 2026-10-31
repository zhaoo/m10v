import {defaultConfiguration,normalizeConfiguration,migrateSimulationSelection,normalizeRawNr,migrateRetiredFilms} from './native-library-state.mjs';
export const extensionFeatures=['halation','digitalHdf','border','timestamp','aspect','level','negativeGrain','rawNr','abCompare','powerImages'];
// Old custom selections remain recoverable in a separate local-storage backup.
export function normalizeWorkbenchDraft(draft={},catalog=[],current=defaultConfiguration()) {
 const hdfOnly=draft.profile==='native'&&draft.features?.includes('digitalHdf')&&!draft.features.includes('film');
 const selected=new Set(draft.features||[]);
 if(draft.imagingSchema!==1&&Object.keys(draft.powerImages||{}).length)selected.add('powerImages');
 const features=[...(hdfOnly?[]:['film']),...extensionFeatures.filter(id=>selected.has(id)&&!(hdfOnly&&['halation','border','timestamp','abCompare'].includes(id)))];
 let configuration=migrateRetiredFilms(draft.nativeConfiguration||current);
 let unresolved=Array.isArray(draft.unresolvedSlots)?draft.unresolvedSlots:[];
 const legacy=draft.profile!=='native'&&draft.features?.includes('film');
 if(legacy){const migrated=migrateSimulationSelection(draft.filmIds||[],draft.filmTexture||{},catalog,configuration);configuration=migrated.configuration;unresolved=migrated.unresolved;}
 configuration.stamp=features.includes('timestamp')?(configuration.stamp||1):0;
 if(!features.includes('timestamp'))configuration.filmNameStamp=false;
 if(!features.includes('digitalHdf'))configuration.hdf=0;
 let rawNr;try{rawNr=normalizeRawNr(draft.rawNr);}catch{rawNr={mode:'stock'};}
 return {...draft,profile:'native',features,nativeConfiguration:configuration,unresolvedSlots:unresolved,recipes:[],stockPresets:[],toolFeaturesDraft:[],rawNr};
}
export function preserveLegacyDraft(storage,key,raw,draft){
 if(draft.profile==='native'&&!draft.features?.some(id=>['recipes','presets'].includes(id)))return;
 const backup=key+'-legacy-backup';
 if(storage.getItem(backup)===null)storage.setItem(backup,raw);
}
