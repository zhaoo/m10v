// This checks the user's explicit camera reading; it does not detect hardware.
const stable={
 gr3:{model:'GR III',version:'2.10',sha256:'d6a3c9c288d784080e7b283222ecdd8752adfeed6faa36dab44f73115354bfd4'},
 gr3x:{model:'GR IIIx',version:'1.60',sha256:'708e79f3b7b96a7e1581b4acf4c412233050a1832718ef7f06c8397db1b431c7'},
};
export function checkCameraForInstall(source,current={}){
 const target=stable[current.model];
 if(!target||!current.version)return {ready:false,message:'请先在相机「设置 → 关于本机 → 固件信息/选项」查看型号与版本，再填写下方选项。'};
 if(['2.20','1.70'].includes(current.version))return {ready:false,message:'机身已安装官方 30 周年纪念固件（2.20 / 1.70），不能使用当前 M10V 刷机。不提供适配、降级或改版本号绕过。'};
 if(current.version!==target.version)return {ready:false,message:'当前机身版本未确认匹配稳定基线，请停止下载并核对机身信息，不要猜测或强刷。'};
 if(!source||source.model!==target.model||source.public_version!==target.version||source.sha256!==target.sha256)
  return {ready:false,message:'所选固件与机身型号或版本不匹配，请返回选择对应内置基线。'};
 return {ready:true,message:`已确认：${target.model} · ${target.version}。这只核对填写信息，仍须按下列步骤操作。`};
}
