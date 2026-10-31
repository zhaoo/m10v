"""Own an independent HDF controller in original TopMenu's extended tail."""
import struct
from scripts.build_gr3_menu_patches import assembly,branch,movw
from scripts.build_gr3_settings_hooks import BASE_VTABLE

def build_hooks(base,symbols,settings,film_library=True,live_color=False,custom_zoom=True,pure_isp_effects=False):
    if type(pure_isp_effects)is not bool:raise ValueError('pure_isp_effects must be bool')
    image=bytearray();exports={}
    def stub(text):
        image.extend(bytes(-len(image)&3));a=base+len(image);image.extend(assembly(text,a));return a
    vt=list(BASE_VTABLE)
    for i,name in [(1,'destroy'),(2,'destroy'),(7,'enter'),(9,'ready'),(10,'key')]:vt[i]=symbols['m10v_hdf_menu_'+name]
    vtable=base+len(image);image.extend(struct.pack('<15I',*vt))
    exports['m10v_hdf_menu_vtable']=stub(f'movw r0,#{vtable&65535};movt r0,#{vtable>>16};bx lr')
    parents={name:symbols['m10v_settings_controller_'+other] for name,other in [('ctor','top_ctor'),('dtor','top_dtor'),('factory','factory'),('key_route','key_route')]} if film_library else {'ctor':0x5319aa68,'dtor':settings['exports']['m10v_settings_top_dtor_original'],'factory':settings['exports']['m10v_settings_factory_original'],'key_route':0x53228c4c}
    exports.update({'m10v_hdf_menu_parent_'+name:a for name,a in parents.items()})
    hdfrow=stub(f'push {{r4,lr}};mov r4,r1;mov r0,r4;mov r1,#0;bl 0x5339de20;mov r0,r4;movw r1,#{1140 if film_library else 970};mov r2,r1;pop {{r4,lr}};b 0x5339dc70')
    rows=settings['rows']+[hdfrow] if film_library else [hdfrow]
    offset=(0x613c if live_color else 0x213c) if film_library else 0x13bc;owner=offset+(0x22c if pure_isp_effects else 0x1c0)
    patches=[]
    def add(a,e,r,n):patches.append(dict(address=a,expected=e,replacement=r,name=n))
    for a,e,name,link in [(0x5316f3b8,0xe300313b,'factory',False),(0x5319667c,0xe1a0c00d,'top_dtor',False),(0x5316fcf8,0xeb00ab5a,'top_ctor',True),(0x53221a4c,0xeb001c7e,'key_route',True)]:add(a,e,branch(a,symbols['m10v_hdf_menu_'+name],link),'HDF menu '+name)
    add(0x5316fcec,0xe30103bc,movw(0,owner),'HDF menu owner size')
    add(0x53b36adc,0x1e1d1b19,((30+len(rows))<<24)|0x1d1b19,'HDF menu root count')
    for i,row in enumerate(rows):
        add(0x53b36bd0+i*8,0,row,'HDF menu row '+str(i))
        add(0x53b36c88+i*4,0x10000000,([0x0200f100,0x0200f101,0x0200f102])[i] if film_library else 0x0200f102,'HDF menu route '+str(i))
    if film_library and custom_zoom:add(0x53b37018,0x02000074,0x0200f105,'Crop selection and focal editor entry')
    metadata=dict(schema='m10v-gr3-hdf-menu/v1',base=base,bytes=len(image),exports=exports,patches=patches,vtable=vtable,rows=rows,owner_offset=offset,owner_bytes=owner,controller_bytes=0x200 if pure_isp_effects else 0x1c0,route=0x0200f102,film_library=film_library,resource_ids=list(range(970,978)),camera_tested=False)
    if pure_isp_effects:
        metadata['effects_cache_owner_offset']=offset+0x200
        metadata['effects_cache_bytes']=44
        metadata['resource_ids']+=list(range(1159,1180))
    return bytes(image),metadata
