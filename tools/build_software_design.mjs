/** 创建 2.4 软件总方案：原生可编辑模块、连接线与表格，保留原参考文件。 */
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import { pathToFileURL } from 'node:url';

const ROOT = 'D:/_UUV';
const RUNTIME = 'C:/Users/Bolin/.cache/codex-runtimes/codex-primary-runtime/dependencies';
const SKILL = 'C:/Users/Bolin/.codex/plugins/cache/openai-primary-runtime/presentations/26.1026.10807/skills/presentations';
const BUILD_ID = new Date().toISOString().replace(/[^0-9]/g, '');
const TMP = path.join(ROOT, '.codex-design-build', BUILD_ID);
const OUTPUT = path.join(ROOT, 'docs/2.4显控仿真软件总方案设计.pptx');
const VALIDATED = path.join(ROOT, '.codex-design-build/finalized', `software-design-${BUILD_ID}.pptx`);
const PREVIEW = path.join(ROOT, 'docs/design-preview');
process.env.RUNTIME_NODE_MODULES = path.join(RUNTIME, 'node/node_modules');
process.env.RUNTIME_NODE = process.execPath;
process.env.RUNTIME_PYTHON = path.join(RUNTIME, 'python/python.exe');
const { Presentation, PresentationFile } = await import(pathToFileURL(path.join(RUNTIME, 'node/node_modules/@oai/artifact-tool/dist/artifact_tool.mjs')).href);
const { finalizePresentation } = await import(pathToFileURL(path.join(SKILL, 'container_tools/artifact_tool_utils.mjs')).href);

await fs.mkdir(TMP, { recursive: true });
await fs.mkdir(PREVIEW, { recursive: true });
await fs.mkdir(path.dirname(VALIDATED), { recursive: true });
const P = Presentation.create({ slideSize: { width: 1280, height: 720 } });
P.theme.defaultFont = '微软雅黑';
const C = { blue: '#4F81BD', darkBlue: '#1F497D', green: '#9BBB59', darkGreen: '#77933C', purple: '#8064A2', darkPurple: '#604A7B', red: '#C0504D', darkRed: '#953735', gray: '#666666', lightBlue: '#DBEEF3', lightGreen: '#EAF1DE', lightPurple: '#E4DFEC', lightRed: '#F2DCDA', white: '#FFFFFF', black: '#222222' };

/** 文字与图形均为原生幻灯片对象，避免把技术图栅格化。 */
function shape(s, name, text, x, y, w, h, fill='none', color=C.black, size=23, lineFill='none', lineStyle='solid', bold=false) {
  const r=s.shapes.add({geometry:'rect', name, position:{left:x,top:y,width:w,height:h}, fill,
    line:{fill:lineFill,width:lineFill==='none'?0:2,style:lineStyle}});
  if(text){r.text=text;r.text.style={typeface:'黑体',fontSize:size,color,bold,alignment:'center',verticalAlignment:'middle',autoFit:'none',insets:5,wrap:'square'};}
  return r;
}
function txt(s,name,text,x,y,w,h,size=20,color=C.black,bold=false,align='left') {
  const r=shape(s,name,text,x,y,w,h,'none',color,size,'none','solid',bold); r.text.style={...r.text.style,alignment:align};return r;
}
function title(s,index,text){
  s.background.fill=C.white;
  const r=txt(s,'title',`➢ 2.4.${index} ${text}`,35,25,1210,60,32,C.blue,true);
  r.text.style={...r.text.style,typeface:'微软雅黑'};
}
function group(s,name,label,x,y,w,h,color){
  const r=shape(s,name,'',x,y,w,h,'none',color,22,color,'dashed');
  txt(s,`${name}-label`,label,x+14,y+7,Math.min(w-28,label.length*24+20),40,24,color,true);
  return r;
}
function block(s,name,text,x,y,w,h,color){return shape(s,name,text,x,y,w,h,color,C.white,24,color);}
function arrow(s,a,b,from='right',to='left',color=C.blue){
  return s.shapes.connect(a,b,{kind:from===to?'elbow':'straight',fromSide:from,toSide:to,line:{fill:color,width:2.4,style:'solid'},tail:{type:'triangle',width:'med',length:'med'}});
}
/** 正交折线按每段保存为原生连接线，最后一段带方向箭头。 */
function route(s,name,points,color=C.blue,dashed=false){
  for(let i=0;i<points.length-1;i++){
    const [x1,y1]=points[i], [x2,y2]=points[i+1];
    s.shapes.add({geometry:'connector',name:`${name}-${i}`,kind:'straight',
      position:{left:Math.min(x1,x2),top:Math.min(y1,y2),width:Math.abs(x2-x1),height:Math.abs(y2-y1),horizontalFlip:x2<x1,verticalFlip:y2<y1},
      line:{fill:color,width:2.4,style:dashed?'dashed':'solid'},
      ...(i===points.length-2?{tail:{type:'triangle',width:'med',length:'med'}}:{})});
  }
}
function footer(s,text='DEMO_UNCALIBRATED　科研原型，所有默认参数与定位结果均未独立标定'){
  txt(s,'evidence-note',text,40,678,1200,25,15,C.gray);
}
function notes(s,text){s.speakerNotes.text=`依据：D:/_UUV/docs/微型潜航器视觉定位仿真技术要求-origin.docx，2.4 显控仿真软件。\n绘图风格参考：D:/_UUV/docs/方案图.pptx。\n实现依据：AGENTS.md、backend/app/contracts/models.py、backend/app/services/runtime.py、backend/app/simulation/engine.py、frontend/src。\n${text}`;}

// 第 1 页：总体模块及前后端职责。
{
 const s=P.slides.add(); title(s,1,'显控仿真软件总体架构');
 group(s,'front','场景想定与显控',42,105,280,505,C.darkGreen);
 group(s,'backend','后端仿真计算权威',350,105,560,505,C.purple);
 group(s,'persistence','数据记录与分发',950,105,285,505,C.blue);
 const config=block(s,'scene-config','场地与相机配置',66,168,232,58,C.green);
 block(s,'target-config','目标与航迹配置',66,251,232,58,C.green);
 const display=block(s,'live-display','三维动态显示',66,365,232,58,C.blue);
 block(s,'replay-display','轨迹与误差回放',66,448,232,58,C.blue);
 txt(s,'front-note','场景保存与加载\n相机位置、高度交互',66,535,232,53,20,C.darkGreen,false,'center');
 const control=block(s,'run-control','配置快照与固定步长调度',386,168,488,58,C.purple);
 const truth=block(s,'truth-generator','运动真值生成',386,263,200,64,C.green);
 const observation=block(s,'observation-generator','观测与误差生成',662,263,212,64,C.purple);
 const vision=block(s,'vision-localization','视觉位置解算',662,379,212,64,C.purple);
 const fusion=block(s,'fusion-adapter','多源定位接入',386,379,200,64,C.red);
 const evaluation=block(s,'evaluation','定位误差评价',386,500,200,64,C.red);
 const publisher=block(s,'event-publisher','统一事件输出',662,500,212,64,C.blue);
 const jsonl=block(s,'jsonl','运行事件 JSONL',975,168,235,58,C.blue);
 const metadata=block(s,'metadata-export','元数据与数据导出',975,270,235,58,C.blue);
 block(s,'sqlite','SQLite 索引',975,372,235,58,C.purple);
 txt(s,'sqlite-note','仅存场景与运行索引',975,435,235,31,17,C.purple,false,'center');
 const ws=block(s,'event-dispatch','实时分发与日志回放',975,480,235,58,C.blue);
 arrow(s,config,control,'right','left',C.darkGreen);
 route(s,'target-to-control',[[298,280],[338,280],[338,197],[386,197]],C.darkGreen);
 route(s,'control-to-truth',[[487,226],[487,263]],C.purple);
 route(s,'control-to-observation',[[768,226],[768,263]],C.purple);
 arrow(s,truth,observation,'right','left',C.darkGreen);
 arrow(s,observation,vision,'bottom','top',C.purple);
 arrow(s,vision,fusion,'left','right',C.purple);
 arrow(s,fusion,evaluation,'bottom','top',C.red);
 route(s,'truth-only-eval',[[386,295],[367,295],[367,532],[386,532]],C.darkGreen,true);
 txt(s,'truth-eval-note','真值评价\n旁路',376,453,104,42,17,C.darkGreen);
 arrow(s,evaluation,publisher,'right','left',C.red);
 route(s,'events-to-jsonl',[[874,532],[930,532],[930,197],[975,197]],C.blue);
 arrow(s,jsonl,metadata,'bottom','top',C.blue);
 route(s,'jsonl-to-replay',[[1210,197],[1223,197],[1223,509],[1210,509]],C.blue);
 route(s,'live-to-ui',[[1092,538],[1092,652],[22,652],[22,394],[66,394]],C.blue);
 txt(s,'live-route-label','实时事件与历史回放数据',485,617,360,29,20,C.blue,false,'center');
 txt(s,'backend-baseline-note','M1：视觉评价与 NoOp 透传，融合对照评价预留',370,575,520,27,17,C.gray,false,'center');
 footer(s);notes(s,'软件总体职责划分。JSONL 是事实来源，SQLite 仅保存索引。运行配置不可变，前端修改草稿后重新启动形成新快照。后端计算光学、定位及误差，前端只进行显示坐标转换和渲染。M1 实际评价三种视觉方法，NoOpFusion 未独立产生融合对照评价，该能力作为后续接入保留。真值可用于观测生成、独立评价与显控，不能进入定位器。');
}

// 第 2 页：等效增量由实际光路计算，不把折射画成任意像素噪声。
{
 const s=P.slides.add(); title(s,2,'参数级等效链路与真值隔离');
 group(s,'forward','参数级等效链路，增量由传播光路计算',40,115,1195,212,C.purple);
 const a=block(s,'truth','UUV 真值位姿',64,183,166,65,C.green);
 const b=block(s,'ideal','几何投影\n理想标记角点',282,183,180,65,C.purple);
 const c=block(s,'flat-delta','平面折射增量',512,183,185,65,C.purple);
 const d=block(s,'wave-delta','波纹折射增量',746,183,185,65,C.purple);
 const e=block(s,'final-observations','最终角点观测',980,183,205,65,C.blue);
 [ [a,b],[b,c],[c,d],[d,e] ].forEach(([x,y])=>arrow(s,x,y,'right','left',C.purple));
 txt(s,'marker-note','已知标记几何',268,265,208,31,19,C.gray,false,'center');
 txt(s,'flat-note','平均界面与折射率',502,265,205,31,19,C.gray,false,'center');
 txt(s,'wave-note','同源时变波场',735,265,208,31,19,C.gray,false,'center');
 txt(s,'association-note','相机 / 目标 / 标记身份',968,265,228,31,18,C.gray,false,'center');
 txt(s,'modes','观测模式：理想针孔、平面 Snell、波纹 Snell',64,335,1000,35,21,C.darkBlue);
 group(s,'inverse','定位、评价与记录',40,392,1195,210,C.blue);
 const f=block(s,'vision-input','定位输入白名单',980,453,205,65,C.blue);
 const g=block(s,'vision-solver','视觉位置解算',746,453,185,65,C.purple);
 const h=block(s,'noop','NoOp 视觉透传',512,453,185,65,C.red);
 const i=block(s,'evaluation','视觉误差评价',282,453,180,65,C.red);
 const j=block(s,'output','记录与显示',64,453,166,65,C.blue);
 arrow(s,e,f,'bottom','top',C.blue);
 [ [f,g],[g,h],[h,i],[i,j] ].forEach(([x,y])=>arrow(s,x,y,'left','right',C.blue));
 route(s,'truth-branch',[[64,215],[20,215],[20,382],[372,382],[372,453]],C.darkGreen,true);
 txt(s,'truth-branch-note','真值评价旁路',407,402,185,29,18,C.darkGreen);
 txt(s,'no-wave-input','真实波面不进入定位器',701,544,284,31,20,C.red,false,'center');
 txt(s,'input-note','标定、观测与历史估计',974,544,221,31,18,C.darkBlue,false,'center');
 txt(s,'delta-flat-equation','Δ平面 = 平面投影 − 理想投影',64,612,535,29,19,C.gray);
 txt(s,'delta-wave-equation','Δ波面 = 波纹投影 − 平面投影',662,612,560,29,19,C.gray);
 txt(s,'scientific-note','真值用于观测生成、独立评价与显控，不进入定位器。解析角点不代表真实图像检测',64,645,1160,28,18,C.gray);
 footer(s);notes(s,'当前实现按模式直接进行正向投影。图中增量是 Δflat=Pflat−Pideal 与 Δwave=Pwavy−Pflat 的参数级等效表达，不是两个任意经验像素偏移。无有效光路时返回无效状态。估计器只使用平均平面、标定和最终观测，不读取真实波纹状态。无校正、平面校正和简单平滑在同一观测批次上比较。M1 计算的是三种视觉方法的误差样本，NoOpFusion 并未独立生成融合对照评价，正式融合对照评价预留给后续研究。真值也可用于显控显示，但不进入定位器。');
}

// 第 3 页：三项研究工作通过稳定的数据契约接入软件底座。
{
 const s=P.slides.add(); title(s,3,'研究算法接入与协作边界');
 const columns=[
  {x:48,color:C.darkGreen,fill:C.green,light:C.lightGreen,title:'2.1 相机布局优化',input:'场地与相机约束\n数量、位置与高度',module:'布局评价与自动求解',output:'相机配置与覆盖指标\n优化状态与质量信息',status:'M1：固定布局，未优化',code:'NOT_OPTIMIZED'},
  {x:456,color:C.purple,fill:C.purple,light:C.lightPurple,title:'2.2 水下视觉定位',input:'多相机角点与标定\n时间与历史估计',module:'折射校正与视觉定位',output:'三维位置与时间戳\n有效性与观测来源',status:'M1：针孔、平面校正与平滑',code:'MODEL_AWARE_DEMO'},
  {x:864,color:C.red,fill:C.red,light:C.lightRed,title:'2.3 多传感器融合',input:'视觉、声学与通信观测\n锚点、坐标与时间映射',module:'时空对齐与融合定位',output:'融合位置与时间戳\n不确定度与测量来源',status:'M1：NoOp 视觉透传',code:'PASSTHROUGH_NOT_FUSED'},
 ];
 for(const [idx,c] of columns.entries()){
  group(s,`algorithm-group-${idx}`,c.title,c.x,120,368,460,c.color);
  const input=shape(s,`algorithm-input-${idx}`,c.input,c.x+24,185,320,72,c.light,C.black,23,c.color);
  const module=block(s,`algorithm-module-${idx}`,c.module,c.x+24,296,320,64,c.fill);
  const output=shape(s,`algorithm-output-${idx}`,c.output,c.x+24,399,320,72,c.light,C.black,23,c.color);
  arrow(s,input,module,'bottom','top',c.color);arrow(s,module,output,'bottom','top',c.color);
  txt(s,`algorithm-status-${idx}`,c.status,c.x+14,495,340,34,20,c.color,false,'center');
  txt(s,`algorithm-code-${idx}`,c.code,c.x+12,535,344,27,17,c.color,false,'center');
 }
 const shared=block(s,'shared-contract','统一数据契约与版本，按注册表和配置切换算法，复用显控、记录与回放',72,616,1136,47,C.blue);
 columns.forEach((c,idx)=>route(s,`adapter-link-${idx}`,[[c.x+184,580],[c.x+184,616]],c.color));
 footer(s,'后续同学提交适配器实现与契约测试，M1 保留可运行基线　　DEMO_UNCALIBRATED');
 notes(s,'对应六类 Protocol：LayoutOptimizer、VisionLocalizer、RefractionModel、WaveSurfaceModel、AcousticRangeSource、FusionLocalizer。输入输出由 Pydantic 模型约束，算法 ID 通过显式注册表和 YAML 选择。M1 固定布局并未优化，NoOpFusion 未对声学或通信观测计权。正式研究算法由后续同学提供。');
}

// 第 4 页：用可编辑表格保持任务指标与当前状态的可核对关系。
{
 const s=P.slides.add(); title(s,4,'课题指标与实施安排');
 txt(s,'mapping-intro','显控仿真底座承担集成，正式研究算法通过约定接口交付',46,92,1180,34,22,C.darkBlue);
 const values=[
  ['课题 2.4 指标','当前 M1 与本轮完善','后续补齐'],
  ['场景参数配置\n保存与加载','矩形场地、相机位置与高度\n目标圆轨迹、深度、数量\n速度由周期推导，配置快照留存','任意航迹与阵型编辑\n自动布局结果联动'],
  ['多源信息实时接入\n显示与状态监视','声学与通信 JSON 接入\n时间窗校验与事件记录\n界面显示有效与过期状态','设备驱动与设备时钟同步\n正式对齐与融合算法'],
  ['动态画面与视觉定位\n多目标轨迹和回放','UUV 与相机模型、轨迹叠加\n后端同源波面采样显示（本轮）\nJSONL 回放与事件追溯','复杂遮挡与识别观测\n真实图像检测另行研究'],
  ['参数级仿真链路\n实时运行与数据导出','几何、折射与波纹光路\n未校正、校正和平滑对比\nYAML、JSONL、元数据与 CSV','按场景规模评价运行速率\n独立数据标定与验证'],
 ];
 const table=s.tables.add({rows:5,columns:3,left:46,top:145,width:1188,height:466,columnWidths:[258,516,414],values});
 table.borders.assign({fill:'#A6B8CD',width:1,style:'solid'});
 for(let r=0;r<5;r++){
  table.rows[r].height=r===0?54:103;
  for(let c=0;c<3;c++){
   const cell=table.getCell(r,c); cell.fill=r===0?C.blue:(c===0?C.lightBlue:(r%2===0?'#F6F8FB':C.white));
   cell.text.style={typeface:'黑体',fontSize:r===0?24:21,color:r===0?C.white:C.black,bold:r===0,alignment:c===0?'center':'left',verticalAlignment:'middle',insets:12,autoFit:'none'};
  }
 }
 txt(s,'mapping-note','评价同时报告位置误差、有效定位率与运行耗时，未标定结果不作为真实设备精度',46,630,1188,34,20,C.darkBlue);
 footer(s);notes(s,'逐项映射原始技术要求 2.4 的四项预期指标。当前实现仍采用水平圆轨迹，速度由半径和周期推导，不宣称独立速度控制、任意航迹或阵型编辑已经完成。后端同源波面采样显示属于本轮接入，最终实现状态由代码与交付记录确认。本页不提供或编造设备精度及性能达标数值。');
}

const candidate=path.join(TMP,'software-design-candidate.pptx');
await (await PresentationFile.exportPptx(P)).save(candidate);
for(const [i,s] of P.slides.items.entries()){
 const blob=await s.export({format:'layout'});
 await fs.writeFile(path.join(TMP,`slide-${i+1}.layout.json`),await blob.text());
}
const reference=path.join(ROOT,'docs/方案图.pptx');
const refSha=crypto.createHash('sha256').update(await fs.readFile(reference)).digest('hex');
const result=await finalizePresentation({
 workspaceDir:ROOT,candidatePath:candidate,finalPath:VALIDATED,
 pythonExecutable:path.join(RUNTIME,'python/python.exe'),
 integrityValidatorPath:path.join(SKILL,'container_tools/inspect_presentation_package_integrity.py'),
 layoutValidatorPath:path.join(SKILL,'container_tools/inspect_presentation_layout_geometry.py'),
 layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-bullet-geometry','--validate-heading-fit','--require-native-table-slide','4'],
 explicitTotalSlideCount:4, requiredNativeTableOwnerSlides:[4], requiredNativeChartOwnerSlides:[],
 fontPolicy:{basis:'reference',families:['微软雅黑','黑体'],referencePath:reference,referenceSha256:refSha},
 verifyArtifactToolImport:true,receiptPath:path.join(TMP,'software-design.validation.json')
});
await fs.copyFile(VALIDATED, OUTPUT);
result.deliveryPath=OUTPUT;
console.log(JSON.stringify(result,null,2));
