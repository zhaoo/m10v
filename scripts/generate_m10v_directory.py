"""Generate ordered camera identities from the shared display directory."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def directory():return json.loads((ROOT/'web/gr3/film-directory.json').read_text())['groups']
def names():return {f['id']:f['name'] for g in directory() for f in g['films']}
def generate():
 groups=directory();films=[(i,f) for i,g in enumerate(groups) for f in g['films']]
 if len(groups)!=6 or len(films)!=46 or len({f['id'] for _,f in films})!=46:raise ValueError('directory identity inventory differs')
 text='/* Generated from web/gr3/film-directory.json. Display order is not identity. */\n#ifndef M10V_FILM_DIRECTORY_H\n#define M10V_FILM_DIRECTORY_H\n#include <stdint.h>\n#define M10V_DIRECTORY_COUNT 46u\n#define M10V_DIRECTORY_GROUPS 6u\n#define M10V_DIRECTORY_GROUP_RESOURCE 1129u\n'
 text+='static const struct {uint16_t id;uint8_t group;char name[24];} m10v_directory[]={\n'
 text+=''.join('{%d,%d,%s},\n'%(f['id'],i,json.dumps(f['name'])) for i,f in films)+'};\n'
 first=[];at=0
 for g in groups:first.append(at);at+=len(g['films'])
 text+='static const uint8_t m10v_directory_first[7]={'+','.join(map(str,first+[at]))+'};\n'
 text+='static inline const char *m10v_directory_name(uint32_t id){for(uint32_t i=0;i<M10V_DIRECTORY_COUNT;i++)if(m10v_directory[i].id==id)return m10v_directory[i].name;return 0;}\n#endif\n'
 return text
if __name__=='__main__':(ROOT/'native/gr3/m10v_film_directory.h').write_text(generate())
