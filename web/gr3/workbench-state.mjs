import {defaultConfiguration,normalizeConfiguration,migrateSimulationSelection,normalizeRawNr,migrateRetiredFilms} from './native-library-state.mjs';
export const extensionFeatures=['halation','digitalHdf','timestamp','aspect','level','negativeGrain','rawNr'];
// Old custom selections remain recoverable in a separate local-storage backup.
export function normalizeWorkbenchDraft(draft={},catalog=[],current=defaultConfiguration()) {
 const hdfOnly=draft.profile==='native'&&draft.features?.includes('digitalHdf')&&!draft.features.includes('film');
 const features=[...(hdfOnly?[]:['film']),...extensionFeatures.filter(id=>draft.features?.includes(id)&&!(hdfOnly&&id==='halation'))];
 let configuration=migrateRetiredFilms(draft.nativeConfiguration||current);
 let unresolved=Array.isArray(draft.unresolvedSlots)?draft.unresolvedSlots:[];
 const legacy=draft.profile!=='native'&&draft.features?.includes('film');
 if(legacy){const migrated=migrateSimulationSelection(draft.filmIds||[],draft.filmTexture||{},catalog,configuration);configuration=migrated.configuration;unresolved=migrated.unresolved;}
 configuration.stamp=features.includes('timestamp')?(configuration.stamp||1):0;
 let rawNr;try{rawNr=normalizeRawNr(draft.rawNr);}catch{rawNr={mode:'stock'};}
 return {...draft,profile:'native',features,nativeConfiguration:configuration,unresolvedSlots:unresolved,recipes:[],stockPresets:[],toolFeaturesDraft:[],rawNr};
}
export function preserveLegacyDraft(storage,key,raw,draft){
 if(draft.profile==='native'&&!draft.features?.some(id=>['recipes','presets'].includes(id)))return;
 const backup=key+'-legacy-backup';
 if(storage.getItem(backup)===null)storage.setItem(backup,raw);
}
