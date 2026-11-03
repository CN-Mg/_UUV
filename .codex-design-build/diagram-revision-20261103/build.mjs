import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { pathToFileURL } from 'node:url';

const root = 'D:/_UUV';
const work = path.join(root, '.codex-design-build/diagram-revision-20261103');
const runtime = 'C:/Users/Bolin/.cache/codex-runtimes/codex-primary-runtime/dependencies';
const skill = 'C:/Users/Bolin/.codex/plugins/cache/openai-primary-runtime/presentations/26.1026.10807/skills/presentations';
const source = path.join(root, 'docs/2.4显控仿真软件总方案设计.pptx');
const reference = path.join(root,'docs/方案图.pptx');
process.env.RUNTIME_NODE_MODULES = path.join(runtime, 'node/node_modules');
process.env.RUNTIME_NODE = process.execPath;
process.env.RUNTIME_PYTHON = path.join(runtime, 'python/python.exe');
const { FileBlob, PresentationFile } = await import(pathToFileURL(path.join(process.env.RUNTIME_NODE_MODULES, '@oai/artifact-tool/dist/artifact_tool.mjs')).href);
const { finalizePresentation } = await import(pathToFileURL(path.join(skill, 'container_tools/artifact_tool_utils.mjs')).href);
const deck = await PresentationFile.importPptx(await FileBlob.load(source));
await fs.writeFile(path.join(work,'source-inspection.ndjson'), (await deck.inspect({kind:'slide,layout,shape,table',maxChars:15000})).ndjson);

const C = {
  white:'#FFFFFF', ink:'#000000', secondary:'#363636', muted:'#585858',
  blue:'#4F81BD', edge:'#000000', rule:'#9DB5CC', pale:'#DBEEF3', fog:'#F6FAFC',
  green:'#58743E', greenEdge:'#111111', sage:'#D6E3BE',
  ochre:'#8B4945', ochreEdge:'#111111', cream:'#F2DCDA',
  purple:'#604A7B', purpleEdge:'#111111', lilac:'#F2DCDA', arrow:'#205867',
};
const body = '微软雅黑';
const mark = '黑体';
const position = (left, top, width, height) => ({left, top, width, height});
function rect(s, name, x, y, w, h, fill='none', stroke='none', dash='solid', weight=1.25) {
  return s.shapes.add({name,geometry:'rect',position:position(x,y,w,h),fill,
    line:{fill:stroke,width:stroke==='none'?0:weight,style:dash}});
}
function label(s, name, value, x, y, w, h, options={}) {
  const {size=20,color=C.ink,bold=false,align='left',inset=0,font=body,fill='none',stroke='none'} = options;
  const shape=rect(s,name,x,y,w,h,fill,stroke);
  shape.text=value;
  shape.text.style={typeface:font,fontSize:size,color,bold,alignment:align,
    verticalAlignment:'middle',autoFit:'none',wrap:'none',insets:inset};
  return shape;
}
function frame(s,name,x,y,w,h,weight=3.3,radius=17) {
  return s.shapes.add({name,geometry:'roundRect',borderRadius:radius,
    position:position(x,y,w,h),fill:'none',line:{fill:C.blue,width:weight,style:'dashed'}});
}
function route(s,name,points,{color=C.arrow,dash='solid',width=1.9,arrow=true}={}) {
  for (let i=1;i<points.length;i++) {
    const [x1,y1]=points[i-1], [x2,y2]=points[i];
    s.shapes.add({name:`${name}-${i}`,geometry:'connector',kind:'straight',
      position:{...position(Math.min(x1,x2),Math.min(y1,y2),Math.abs(x2-x1),Math.abs(y2-y1)),
        horizontalFlip:x2<x1,verticalFlip:y2<y1},line:{fill:color,width,style:dash},
      ...(arrow && i===points.length-1?{tail:{type:'triangle',width:'med',length:'med'}}:{})});
  }
}
const rule=(s,name,x1,y,x2,color=C.rule)=>route(s,name,[[x1,y],[x2,y]],{color,width:1,arrow:false});
const vertical=(s,name,x,y1,y2)=>route(s,name,[[x,y1],[x,y2]],{color:C.rule,width:1,arrow:false});
function node(s,name,title,detail,x,y,w,h,{fill=C.pale,stroke=C.edge,color=C.ink,detailColor=C.secondary,align='center',size=22,sub=16}={}) {
  rect(s,`${name}-边框`,x,y,w,h,fill,stroke);
  const pad=align==='center'?0:12;
  if (!detail) return label(s,name,title,x+pad,y,w-pad*2,h,{size,color,bold:true,align});
  label(s,name,title,x+pad,y+7,w-pad*2,27,{size,color,bold:true,align});
  label(s,`${name}-说明`,detail,x+pad,y+33,w-pad*2,h-38,{size:sub,color:detailColor,align});
}
function title(s,index,value) {
  s.background.fill=C.white;
  label(s,'页面标题',`➢ 2.4.${index} ${value}`,36,35,1190,51,{size:31,color:C.blue,bold:true});
}
function footer(s,index) {
  label(s,'证据状态','DEMO_UNCALIBRATED',56,674,205,24,{size:15,font:mark,color:C.blue});
  label(s,'证据说明','M1 科研原型，默认参数与仿真结果未经独立标定',270,674,860,24,{size:15,color:C.muted});
  label(s,'页码',`${index} / 4`,1160,674,64,24,{size:15,color:C.muted,align:'right'});
}
const notes=(s,refs,detail)=>{s.speakerNotes.text=[...refs, '', detail].join('\n');};
const docs='D:/_UUV/docs/';
const visionRef=docs+'algorithm-interfaces.md';
const release=docs+'release-20261103.md';
const original=docs+'微型潜航器视觉定位仿真技术要求-origin.docx，第 2.4 节';
const gen='D:/_UUV/backend/app/simulation/engine.py';
const runtimeRef='D:/_UUV/backend/app/services/runtime.py';
for (const slide of deck.slides.items) {
  for (const shape of [...slide.shapes.items]) shape.delete();
}

{
  const s=deck.slides.items[0];
  title(s,1,'显控仿真软件总体架构');
  frame(s,'前端显控边界',50,112,213,419);
  frame(s,'后端边界',283,112,600,442);
  frame(s,'记录分发边界',914,112,319,419);
  label(s,'前端区标题','前端显控',64,120,190,31,{size:22,bold:true});
  label(s,'后端区标题','后端仿真计算',304,120,240,31,{size:22,bold:true});
  label(s,'记录区标题','运行记录与分发',929,120,290,31,{size:22,bold:true});

  node(s,'场景配置与控制','场景配置与控制','编辑、保存与加载场景\n启动 / 暂停 / 继续 / 停止',64,169,185,87,{align:'left',size:21,sub:14});
  const picture=path.join(root,'assets/scenes/m1_tank_preview.png');
  s.images.add({blob:await fs.readFile(picture),contentType:'image/png',alt:'M1 水池场景示意，含 UUV 与相机视锥',
    fit:'contain',position:position(64,274,185,132)});
  label(s,'场景图片题注','M1 水池场景示意',64,409,185,20,{size:14,color:C.muted,align:'center'});
  node(s,'三维显控','三维显示与回放','轨迹、波面和误差曲线',64,447,185,65,{align:'left',size:20,sub:15});

  node(s,'固定步长调度','配置快照与固定步长调度','启动时锁定配置，按仿真步推进',305,169,555,74,{align:'center'});
  route(s,'运行请求',[[249,211],[305,211]]);
  route(s,'按步生成真值',[[379,243],[379,281]]);
  node(s,'运动真值','运动真值','目标位姿',305,281,148,62,{fill:C.sage});
  node(s,'生成角点观测','角点观测生成','几何与折射光路',493,281,160,62,{fill:C.lilac});
  node(s,'视觉定位','视觉定位','位置、时刻、有效性',692,281,168,62);
  route(s,'真值生成观测',[[453,312],[493,312]]);
  route(s,'观测进入定位',[[653,312],[692,312]]);

  node(s,'独立评价','独立视觉评价','同帧真值与视觉估计',481,416,172,64,{fill:C.sage,sub:15});
  node(s,'透传分支','NoOp 视觉透传','仅采用有效主视觉估计',692,416,168,64,{fill:C.cream,size:20,sub:14});
  route(s,'视觉估计用于评价',[[776,343],[776,375],[567,375],[567,416]]);
  route(s,'主估计用于透传',[[776,375],[776,416]]);
  route(s,'真值评价旁路',[[379,343],[379,448],[481,448]],{color:C.green,dash:'dashed'});
  label(s,'真值旁路标注','真值旁路',389,425,84,20,{size:15,color:C.green});
  route(s,'评价事件',[[567,480],[567,514]],{arrow:false});
  route(s,'透传事件',[[776,480],[776,514]],{arrow:false});
  route(s,'统一事件记录',[[567,514],[905,514],[905,309],[929,309]]);
  label(s,'事件汇聚标注','统一运行事件（真值、观测、估计、评价等）',316,521,545,23,{size:16,color:C.blue});

  label(s,'元数据与索引','metadata.json 保存配置与版本\nSQLite 保存场景与运行索引',929,174,290,69,{size:17,color:C.secondary});
  rule(s,'记录区分隔',929,246,1218);
  node(s,'JSONL运行事实','运行事件 JSONL','按 event_seq 追加并落盘',929,278,289,62,{fill:C.sage});
  node(s,'实时流','实时推送','WebSocket',929,390,131,66,{size:19,sub:16});
  node(s,'回放流','历史回放','按序读取 JSONL',1087,390,131,66,{size:19,sub:14});
  route(s,'落盘后实时推送',[[1073,340],[1073,363],[994,363],[994,390]]);
  route(s,'日志进入历史回放',[[1073,363],[1152,363],[1152,390]]);
  route(s,'实时事件进入显示',[[994,456],[994,574]],{arrow:false});
  route(s,'回放事件进入显示',[[1152,456],[1152,574],[156,574],[156,512]]);
  label(s,'显示数据流标签','实时事件与历史回放共用显示逻辑',401,586,470,30,{size:18,color:C.blue,align:'center'});
  footer(s,1);
  notes(s,[original,gen,runtimeRef,picture],'仿真、定位与评价在后端完成。前端的场景编辑作用于草稿。暂停等待当前仿真步落盘，历史回放按 event_seq 读既有日志。图中独立评价和 NoOp 透传为并行分支。统一运行事件还包含波面及适用的声学和通信观测。');
}

{
  const s=deck.slides.items[1];
  title(s,2,'参数级观测生成与真值隔离');
  frame(s,'正向仿真边界',45,106,1191,251);
  frame(s,'投影模式分组',347,140,314,202,1.3,14);
  frame(s,'定位与评价边界',45,380,1191,174);
  label(s,'正向标题','正向仿真',62,114,200,29,{size:22,bold:true});
  node(s,'光学生成输入','真值位姿与标记几何','相机标定与当前时刻',62,208,218,66,{fill:C.sage,size:20});
  label(s,'光路选择标签','由场景选择一种投影模式',359,111,290,27,{size:17,color:C.ink});
  const modes=[
    ['理想针孔','几何投影'],
    ['平面 Snell','平均界面与折射率'],
    ['波纹 Snell','瞬时界面与局部法向'],
  ];
  modes.forEach(([name,desc],i)=>{
    const y=147+68*i;
    rect(s,`${name}-光路模块`,359,y,290,51,i===0?C.pale:C.lilac,C.edge);
    label(s,name,name,371,y,119,51,{size:20,bold:true});
    label(s,`${name}-条件`,desc,488,y,153,51,{size:16,color:C.secondary});
    route(s,`${name}-输入`,[[323,241],[323,y+25],[359,y+25]]);
    route(s,`${name}-输出`,[[649,y+25],[693,y+25],[693,241]],{arrow:false});
  });
  route(s,'光路择一输入',[[280,241],[323,241]],{arrow:false});
  route(s,'选定投影进入观测',[[693,241],[767,241]]);
  node(s,'最终角点','最终像素角点','可见性与图像边界检查，可选像素噪声',767,208,457,66,{size:22,sub:16});
  label(s,'投影差值','Δ平面 = 平面投影 − 理想投影\nΔ波面 = 波纹投影 − 平面投影',768,282,375,62,{size:17,color:C.secondary});

  label(s,'解算与评价标题','视觉解算与独立评价',62,389,395,31,{size:22,bold:true});
  node(s,'定位输入白名单','标定参数与历史估计','相机、标记、平均水面\n历史估计及其不确定度',62,442,224,94,{align:'left',fill:C.sage,size:20});
  node(s,'视觉对照方法','同批观测的三种视觉估计','无校正、平面校正、校正加平滑\n输出位置、估计时刻与有效性',386,442,356,94,{align:'left',size:21});
  node(s,'独立评价输出','位置误差与有效定位率','共同有效帧比较 RMSE、MAE、P95\n各方法单列有效率与失败原因',844,442,375,94,{align:'left',fill:C.sage,size:21});
  route(s,'标定历史进入定位',[[286,489],[386,489]]);
  route(s,'最终观测进入定位',[[1172,274],[1172,368],[564,368],[564,442]]);
  route(s,'估计进入独立评价',[[742,489],[844,489]]);
  route(s,'真值独立评价路径',[[62,241],[27,241],[27,589],[1034,589],[1034,536]],{color:C.green,dash:'dashed'});
  label(s,'真值评价标注','真值旁路（同一仿真时刻）',417,554,342,29,{size:17,color:C.green,align:'center'});
  label(s,'估计器隔离说明','定位器只接收最终角点、标定与历史估计。角点由解析投影生成，目标与标记关联由仿真预先给定。',56,620,1168,26,{size:17,color:C.secondary});
  footer(s,2);
  notes(s,[original,gen,visionRef,docs+'experiments.md'],'三种模式分别直接求解各自的正向几何，差值用于解释参数级等效扰动。波纹模式的生成端共享后端波场。M1 的视觉估计器不接触真值位姿、瞬时波面或波场种子。无校正、平面校正和简单平滑比较同批观测，失败样本计入有效率。NoOp 为独立透传，见第 1、3 页。');
}

{
  const s=deck.slides.items[2];
  title(s,3,'研究算法接口与 M1 基线');
  const cols=[
    ['研究任务',56,176],['主要输入',240,215],['适配器',479,188],
    ['输出契约',691,236],['M1 当前状态',946,278],
  ];
  for (const [value,x,w] of cols) label(s,value,value,x+9,120,w-18,38,{size:18,bold:true,color:C.ink});
  const rows=[
    {id:'2.1',task:'相机布局',input:'场地与相机标定\n数量、候选位置、高度约束',adapter:'LayoutOptimizer',secondary:'evaluate / optimize',out:'相机布局与评价指标\n优化状态',status:'固定布局，返回覆盖评价',code:'NOT_OPTIMIZED',fill:C.sage,edge:C.greenEdge,color:C.green},
    {id:'2.2',task:'水下视觉定位',input:'多相机角点、标定与时间\n可选历史估计',adapter:'VisionLocalizer',secondary:'localize',out:'三维位置与估计时刻\n有效性和测量来源',status:'基线比较针孔、校正与平滑',code:'MODEL_AWARE_DEMO',fill:C.pale,edge:C.edge,color:C.purple},
    {id:'2.3',task:'多传感器融合',input:'视觉、声学与通信观测\n锚点、外参与时间映射',adapter:'FusionLocalizer',secondary:'reset / update',out:'位置与参考时刻\n有效性和实际使用的观测 ID',status:'NoOp 透传有效主视觉估计',code:'PASSTHROUGH_NOT_FUSED',fill:C.cream,edge:C.ochreEdge,color:C.ochre},
  ];
  rows.forEach((r,i)=>{
    const y=165+111*i;
    frame(s,`${r.id}-研究任务分组`,53,y+2,1174,101,2.1,14);
    label(s,`${r.id}-编号`,r.id,65,y+13,151,28,{size:22,bold:true,color:r.color});
    label(s,`${r.id}-任务`,r.task,65,y+42,163,29,{size:21,bold:true});
    label(s,`${r.id}-输入`,r.input,249,y+15,200,80,{size:16});
    node(s,r.adapter,r.adapter,r.secondary,478,y+22,182,65,{fill:r.fill,stroke:r.edge,size:17,sub:14});
    route(s,`${r.id}-输入交接`,[[455,y+55],[478,y+55]]);
    route(s,`${r.id}-输出交接`,[[660,y+55],[683,y+55]]);
    label(s,`${r.id}-输出`,r.out,696,y+15,232,80,{size:16});
    label(s,`${r.id}-M1实现`,r.status,955,y+25,267,26,{size:17,bold:true,color:r.color});
    label(s,`${r.id}-M1状态码`,r.code,955,y+55,269,24,{size:16,font:mark,color:C.secondary});
  });
  frame(s,'共用接口说明分组',53,505,1174,88,1.15,12);
  label(s,'辅助接口','辅助接口',65,517,146,27,{size:18,color:C.blue,bold:true});
  label(s,'辅助接口说明','RefractionModel  管光路    WaveSurfaceModel  供波面采样    AcousticRangeSource  读测距观测',220,517,1004,27,{size:17,color:C.secondary});
  label(s,'联调关系','联调关系',65,554,146,27,{size:18,color:C.blue,bold:true});
  label(s,'课题交接说明','2.1 布局应用到场景待联调。2.2 主视觉估计已进入 2.3 接口，声学与通信观测单独接入。',220,554,1004,27,{size:17,color:C.secondary});
  label(s,'适配器替换说明','替换研究算法时，通过显式注册表与 YAML 选择实现，复用版本化数据契约、事件记录与回放。',65,604,1159,30,{size:17,color:C.blue});
  footer(s,3);
  notes(s,[original,visionRef,release,gen],'2.1 固定布局评价仍输出 NOT_OPTIMIZED，优化返回结果应用到场景需另行联调。MODEL_AWARE_DEMO 指使用平均界面参数的校正分支。2.3 的输入可保留异步观测与源时钟信息。当前 NoOp 只使用主视觉估计，正式对齐与融合待研究算法接入。');
}

{
  const s=deck.slides.items[3];
  title(s,4,'课题指标与 M1 交付范围');
  const values=[
    ['课题 2.4 指标','M1 已交付','后续工作'],
    ['场景参数配置\n保存与加载','配置场地、相机位置与高度、目标数量和深度\n圆轨迹速度由半径和周期推导，运行保留配置快照','任意航迹与阵型编辑\n布局结果预览并应用到场景'],
    ['多源信息接入\n显示与状态监视','接收已映射至仿真时钟的声学与通信数据\n显示采样时刻、龄期和有效状态，保留观测事件','设备驱动与设备时钟同步\n正式时空对齐与融合验证'],
    ['动态仿真画面\n多目标轨迹与回放','显示 UUV、相机、真值和估计轨迹\n渲染同源波面（21 × 21 采样），按事件序列回放','复杂遮挡与真实图像检测\n真实多目标关联验证'],
    ['参数级位姿链路\n运行与数据导出','生成真值位姿，求解视觉位置并作误差对照\n保留 YAML 配置、JSONL、元数据和 CSV','补充姿态估计及评价\n分规模测量运行速率，开展独立标定'],
  ];
  const table=s.tables.items[0];
  table.position=position(56,126,1168,472);
  [228,525,415].forEach((width,column)=>{table.columns.get(column).width=width;});
  table.borders.assign({fill:C.rule,width:1,style:'solid'});
  for (let r=0;r<5;r++) {
    table.rows[r].height=r===0?48:106;
    for (let c=0;c<3;c++) {
      const cell=table.getCell(r,c);
      cell.value=values[r][c];
      cell.fill=r===0?C.blue:(c===0?C.pale:(r%2===0?C.fog:C.white));
      cell.text.style={typeface:body,fontSize:r===0?21:19,
        color:r===0?C.white:C.ink,bold:r===0||c===0,alignment:'left',
        verticalAlignment:'middle',insets:{left:15,right:12,top:7,bottom:7},autoFit:'none'};
    }
  }
  label(s,'评价口径','验收记录分别保留定位误差、有效定位率与实际运行速率。',56,617,1168,29,{size:19,color:C.blue});
  footer(s,4);
  notes(s,[original,release,docs+'known-limitations.md',docs+'experiments.md'],'2.4 的原要求包含位姿链路与实时运行。M1 当前输出真值位姿和视觉位置估计。固定步长与实际墙钟运行速率分别记录。后端与光学计算共用波场实例，显示倍率不改变物理振幅。正式研究算法、设备联试与独立水池验证按后续工作列示。');
}

const build=process.argv[2] ?? '01';
const candidate=path.join(work,`candidate-${build}.pptx`);
const styledCandidate=path.join(work,`styled-candidate-${build}.pptx`);
const finalPath=path.join(work,'final',`validated-${build}.pptx`);
await fs.mkdir(path.dirname(finalPath),{recursive:true});
await (await PresentationFile.exportPptx(deck)).save(candidate);
execFileSync(process.env.RUNTIME_PYTHON,[path.join(work,'title-shadow.py'),reference,candidate,styledCandidate]);
const result=await finalizePresentation({
  workspaceDir:root,candidatePath:styledCandidate,finalPath,
  pythonExecutable:process.env.RUNTIME_PYTHON,
  integrityValidatorPath:path.join(skill,'container_tools/inspect_presentation_package_integrity.py'),
  layoutValidatorPath:path.join(skill,'container_tools/inspect_presentation_layout_geometry.py'),
  layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-heading-fit','--require-native-table-slide','4'],
  explicitTotalSlideCount:4,requiredNativeTableOwnerSlides:[4],
  fontPolicy:{basis:'reference',families:[body,mark],referencePath:reference,
    referenceSha256:crypto.createHash('sha256').update(await fs.readFile(reference)).digest('hex')},
  verifyArtifactToolImport:true,receiptPath:path.join(work,`validation-${build}.json`),
});
console.log(JSON.stringify(result,null,2));
