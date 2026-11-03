import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { pathToFileURL } from 'node:url';

const root='D:/_UUV';
const work=path.join(root,'.codex-design-build/overview-reflow-20261103');
const skill='C:/Users/Bolin/.codex/plugins/cache/openai-primary-runtime/presentations/26.1026.10807/skills/presentations';
const runtime='C:/Users/Bolin/.cache/codex-runtimes/codex-primary-runtime/dependencies';
process.env.RUNTIME_NODE=process.execPath;
process.env.RUNTIME_NODE_MODULES=path.join(runtime,'node/node_modules');
process.env.RUNTIME_PYTHON=path.join(runtime,'python/python.exe');
const {Presentation,PresentationFile,FileBlob}=await import(pathToFileURL(path.join(process.env.RUNTIME_NODE_MODULES,'@oai/artifact-tool/dist/artifact_tool.mjs')).href);
const {finalizePresentation}=await import(pathToFileURL(path.join(skill,'container_tools/artifact_tool_utils.mjs')).href);

const source=path.join(work,'source/source.pptx');
const reference=await PresentationFile.importPptx(await FileBlob.load(source));
if (reference.slides.items.length!==3) throw Error('Unexpected source slide count');
const inspection=await reference.inspect({kind:'slide,layout,shape,image',maxChars:16000});
await fs.writeFile(path.join(work,'source-inspection.ndjson'),inspection.ndjson);

const deck=Presentation.create({slideSize:{width:1280,height:720}});
const slide=deck.slides.add();
const colors={black:'#000000',dark:'#303030',muted:'#555555',blue:'#4F81BD',
  sky:'#DBEEF3',pink:'#F2DCDA',green:'#D7E4BD',arrow:'#205867',truth:'#597448'};
const font='微软雅黑';
const frame=(left,top,width,height)=>({left,top,width,height});
function box(name,x,y,w,h,fill) {
  return slide.shapes.add({name,geometry:'rect',position:frame(x,y,w,h),fill,
    line:{fill:colors.black,width:1.15,style:'solid'}});
}
function group(name,x,y,w,h,inner=false) {
  return slide.shapes.add({name,geometry:'roundRect',position:frame(x,y,w,h),fill:'none',
    adjustmentList:[{name:'adj',formula:'val 10500'}],
    line:{fill:colors.blue,width:inner?1.3:3.25,style:'dashed'}});
}
function txt(name,text,x,y,w,h,{size=18,bold=false,color=colors.black,align='center',typeface=font}={}) {
  const shape=slide.shapes.add({name,geometry:'textbox',position:frame(x,y,w,h),fill:'none',line:{fill:'none',width:0}});
  shape.text=text;
  shape.text.style={typeface,fontSize:size,bold,color,alignment:align,verticalAlignment:'middle',
    autoFit:'none',wrap:'none',insets:0};
  return shape;
}
function module(name,title,detail,x,y,w,h,fill,{size=22,sub=16}={}) {
  box(name+'边框',x,y,w,h,fill);
  if (!detail) {
    txt(name,title,x+5,y+4,w-10,h-8,{size,bold:true});
    return;
  }
  txt(name,title,x+5,y+5,w-10,28,{size,bold:true});
  txt(name+'说明',detail,x+5,y+33,w-10,h-37,{size:sub,color:colors.dark});
}
function wire(name,points,{color=colors.arrow,dash='solid',arrow=true,width=2}={}) {
  for(let i=1;i<points.length;i++) {
    const [x1,y1]=points[i-1], [x2,y2]=points[i];
    if (x1===x2 && y1===y2) continue;
    slide.shapes.add({name:`${name}-${i}`,geometry:'connector',kind:'straight',
      position:{...frame(Math.min(x1,x2),Math.min(y1,y2),Math.abs(x2-x1),Math.abs(y2-y1)),
        horizontalFlip:x2<x1,verticalFlip:y2<y1},
      line:{fill:color,width,style:dash},
      ...(arrow && i===points.length-1?{tail:{type:'triangle',width:'med',length:'med'}}:{})});
  }
}

// 延续原稿三栏。场景组成放在计算链路上方，左栏保留配置入口和原水池图。
group('前端显控边界',50,125,207,478);
group('后端仿真计算边界',283,125,620,478);
group('记录分发边界',930,125,303,478);
txt('前端显控栏标题','前端显控',60,136,187,34,{size:24,bold:true});
txt('仿真计算栏标题','后端仿真计算',296,136,594,34,{size:24,bold:true});
txt('记录分发栏标题','运行记录与分发',940,136,283,34,{size:24,bold:true});

module('场景配置与运行控制','场景配置与运行控制','编辑、保存与加载场景\n启动、暂停、继续、停止',64,202,179,78,colors.sky,{size:17,sub:14});
txt('水池图题注','水池仿真场景示意',64,435,179,23,{size:15,color:colors.muted});
module('三维显示与回放','三维显示与回放','轨迹、波面和误差曲线',64,478,179,68,colors.sky,{size:20,sub:15});

group('场景构建分组',295,178,596,107,true);
txt('仿真场景构建','仿真场景构建',305,181,576,27,{size:21,bold:true});
const components=[
  {x:305,title:'水池与坐标系',detail:'池长、池宽、水深\n坐标原点与轴向',color:colors.green},
  {x:452,title:'UUV 与航迹',detail:'艇数、标记几何\n深度、圆轨迹',color:colors.green},
  {x:599,title:'相机布设与标定',detail:'数量、位置、高度\n朝向、内参和外参',color:colors.sky},
  {x:746,title:'水面与光学条件',detail:'投影模式、折射率\n波幅、周期',color:colors.pink},
];
for (const c of components) module(c.title,c.title,c.detail,c.x,210,135,66,c.color,{size:16.5,sub:13});
wire('场景配置输入',[[243,241],[295,241]]);
wire('场地与运动输入横线',[[372.5,276],[372.5,296],[519.5,296],[519.5,276]],{arrow:false});
wire('场地与运动输入',[[382,296],[382,346]]);
txt('场地与运动输入标注','场地与运动参数',390,307,137,22,{size:14,color:colors.arrow,align:'left'});
wire('成像条件横线',[[666.5,276],[666.5,296],[813.5,296],[813.5,276]],{arrow:false});
wire('成像条件输入',[[666.5,296],[666.5,327],[590,327],[590,346]]);
txt('成像条件输入标注','成像条件',676,306,93,20,{size:14,color:colors.arrow,align:'left'});

module('运动真值','运动真值','目标位置与姿态',305,346,154,65,colors.green);
module('角点观测生成','角点观测生成','几何投影与水面折射',509,346,162,65,colors.pink,{size:21,sub:15});
module('视觉定位','视觉定位','位置、时刻、有效性',713,346,168,65,colors.sky,{size:22,sub:15});
wire('真值供观测生成',[[459,379],[509,379]]);
wire('角点进入定位',[[671,379],[713,379]]);

module('独立视觉评价','独立视觉评价','同帧真值与各视觉估计',482,470,189,71,colors.green,{size:21,sub:15});
module('多源定位接口','多源定位接口','声学与通信观测接入\nM1 透传有效主视觉估计',713,470,168,71,colors.pink,{size:20,sub:13});
wire('定位分支到评价',[[797,411],[797,437],[576.5,437],[576.5,470]]);
wire('定位分支到多源接口',[[797,437],[797,470]]);
wire('真值旁路',[[382,411],[382,505],[482,505]],{color:colors.truth,dash:'dashed'});
txt('真值旁路标注','真值旁路',392,480,78,20,{size:15,color:colors.truth,align:'left'});

module('场景与运行档案','场景与运行档案','场景配置与版本信息\n场景和运行索引',944,202,275,78,colors.green,{size:22,sub:16});
module('运行事件日志','运行事件日志','JSONL 按事件序号保存',944,346,275,65,colors.green,{size:22,sub:16});
module('实时推送','实时推送','WebSocket',944,478,128,68,colors.sky,{size:20,sub:14});
module('历史回放','历史回放','按序读取事件',1091,478,128,68,colors.sky,{size:20,sub:14});

wire('评价事件加入汇总',[[576.5,541],[576.5,563]],{arrow:false});
wire('定位输出加入汇总',[[797,541],[797,563]],{arrow:false});
wire('运行事件写入日志',[[576.5,563],[915,563],[915,379],[944,379]]);
txt('运行事件汇总说明','运行事件汇总（真值、观测、估计与评价）',566,569,326,22,{size:14,color:colors.arrow});
wire('日志供实时推送',[[1081.5,411],[1081.5,447],[1008,447],[1008,478]]);
wire('日志供历史回放',[[1081.5,447],[1155,447],[1155,478]]);
wire('实时推送接显示',[[1008,546],[1008,629]],{arrow:false});
wire('历史回放接显示',[[1155,546],[1155,629],[153.5,629],[153.5,546]]);
txt('显示回路标签','实时事件与历史事件供前端显示',435,639,411,26,{size:17,color:colors.arrow});
txt('未标定证据标签','DEMO_UNCALIBRATED   M1 参数级仿真，默认参数与结果未经独立标定',
  50,680,1183,21,{size:13.5,color:colors.muted,align:'left'});

const build=process.argv[2] ?? '01';
const donor=path.join(work,`overview-${build}.pptx`);
const candidate=path.join(work,`candidate-${build}.pptx`);
const finalPath=path.join(work,'final',`overview-${build}.pptx`);
await fs.mkdir(path.dirname(finalPath),{recursive:true});
await (await PresentationFile.exportPptx(deck)).save(donor);
execFileSync(process.env.RUNTIME_PYTHON,[path.join(work,'replace-overview.py'),source,donor,candidate]);
const result=await finalizePresentation({
  workspaceDir:root,candidatePath:candidate,finalPath,
  pythonExecutable:process.env.RUNTIME_PYTHON,
  integrityValidatorPath:path.join(skill,'container_tools/inspect_presentation_package_integrity.py'),
  layoutValidatorPath:path.join(skill,'container_tools/inspect_presentation_layout_geometry.py'),
  layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-heading-fit'],
  explicitTotalSlideCount:3,verifyArtifactToolImport:true,
  receiptPath:path.join(work,`validation-${build}.json`),
});
const hash=crypto.createHash('sha256').update(await fs.readFile(source)).digest('hex');
console.log(JSON.stringify({sourceSha256:hash,output:result.finalPath,layout:result.presentationLayout},null,2));
