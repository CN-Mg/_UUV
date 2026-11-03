# 2.1–2.3 独立联调入口

本文配套 `algorithm-interfaces.md` 和后端权威 `contracts.schema.json`。这些接口用于接入同学自己的实现，不表示 M1 已完成布局优化或多源融合。所有样例仍为 `DEMO_UNCALIBRATED`。

## 启动与发现

用 `tools/start_backend.ps1` 启动指定 UUV Python 环境的后端，地址 `http://127.0.0.1:8010`。`GET /api/adapters` 返回注册算法 ID、实际声明版本、支持的契约版本、能力和占位状态；`/docs` 提供模型和调用说明。

## 2.1 布局评价与求解

```powershell
$base = 'http://127.0.0.1:8010'
$scene = Invoke-RestMethod "$base/api/scenarios/demo_uncalibrated"
$request = @{
  tank = $scene.tank; cameras = $scene.cameras
  depths_m = @(1.0); grid_size = 7; camera_count = 3
  height_bounds_m = @(1.0, 2.5)
}
$body = @{algorithm_id='fixed_layout_v1';request=$request} | ConvertTo-Json -Depth 30
Invoke-RestMethod "$base/api/layout/optimize" -Method Post -ContentType 'application/json' -Body $body
```

`POST /api/layout/evaluate` 接收 `LayoutEvaluationRequest`，评价请求中不带 `camera_count` 或优化约束；`POST /api/layout/optimize` 接收 `LayoutRequest`。两者都包装为 `{algorithm_id,request}`。

固定实现返回 `NOT_OPTIMIZED`；缺失或违反约束的配置不得假装优化成功。正式同学可返回候选集内的最优布局，但必须声明评价假设和误差模型。几何覆盖与交会角不是已标定定位精度；未计算的位置不确定度为空。

## 2.2 视觉单帧

```powershell
$request = Get-Content 'tests/contracts/fixtures/vision-request.json' -Raw | ConvertFrom-Json
$body = @{algorithm_id='flat_snell_baseline_v1';request=$request} | ConvertTo-Json -Depth 40
$vision = Invoke-RestMethod "$base/api/vision/localize" -Method Post -ContentType 'application/json' -Body $body
```

请求只有最终像素观测、白名单标定、目标/时间和可选历史估计，没有真值、航迹、生成种子或真实瞬时波面。输出目标、时间、版本、坐标、有限性及来源均受校验。正式识别算法、波纹抑制方法可替换视觉适配器。

## 2.3 一次融合更新

```powershell
$batch = @{target_id=$request.target_id;sim_time_s=$request.sim_time_s;vision=$vision;acoustic=@();communication=@()}
$body = @{algorithm_id='noop_fusion_v1';batch=$batch} | ConvertTo-Json -Depth 40
Invoke-RestMethod "$base/api/fusion/update" -Method Post -ContentType 'application/json' -Body $body
```

调用包装 `{algorithm_id,context,batch}`；省略 `context` 时使用默认未标定上下文。上下文提供锚点、`T_world_sensor` 外参、已知设备时钟比例/偏移、误差模型和时间容差。批次中的各测量保留自身时间和来源，通信转发的视觉位置不能视为独立观测。

`NoOpFusion` 实际只透传视觉，并列出来源，输出 `PASSTHROUGH_NOT_FUSED`。未知设备时钟的估计、完整时空对齐与正式融合仍由 2.3 算法实现。

## 连续调用与接入步骤

以上单帧 REST 联调接口每次创建独立适配器实例；不会在无运行 ID 的 HTTP 请求之间隐式保留滤波状态。连续算法通过 `POST /api/runs` 选择 YAML 中的算法 ID，运行引擎为每个运行/目标隔离状态。

1. 实现对应 Protocol 与输出契约，声明自身算法 ID/版本。
2. 在显式注册表注册工厂、版本、能力与支持的契约版本。
3. 使用 JSON 样例和契约测试验证，再替换 YAML 的适配器 ID。
4. 保存配置快照后运行；记录科学事件、错误状态和版本。不修改前端的定位逻辑，也不把真值加入算法输入。

建议的下一步任务：每位同学先接入一个最小实现，使用上述独立入口完成一次合法输入、一次非法输入和一次失败状态联调，再进行方法研究。
