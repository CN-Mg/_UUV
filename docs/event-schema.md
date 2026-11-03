# 事件与回放契约

所有事件使用同一个外壳，单位为 m、s、rad、px，坐标为 `LOCAL_TANK_RH`，证据状态为 `DEMO_UNCALIBRATED`。

```json
{
  "scenario_id": "demo_uncalibrated",
  "run_id": "本次运行的 UUID",
  "sim_time_s": 0.0,
  "event_seq": 1,
  "event_type": "run_status",
  "schema_version": "1.0",
  "payload": {"status": "running", "speed": 1.0}
}
```

`event_seq` 在单次运行中从 1 开始严格递增。同一仿真时刻会产生多个事件，不能只按浮点时间排序。`sim_time_s` 是事件发布时当前数学时间；观测 payload 中的 `measurement_time_s` 是观测时刻，`received_sim_time_s` 是已映射到仿真时钟的接收时刻。原始设备时间和坐标来源可用 `source_time_s`、`source_clock_id`、`source_frame_id` 保留。

| 类型 | payload 内容与用途 |
| --- | --- |
| `run_status` | 生命周期、倍速、控制动作或错误原因 |
| `uuv_truth` | 目标 ID、世界位置、航向等；仅供显示和评价 |
| `camera_observation` | 相机/目标/标记身份、四角像素、观测时刻与解析观测标识 |
| `vision_estimate` | 算法/目标、参考时刻、位置、有效性、质量、来源测量 ID |
| `fusion_estimate` | 融合契约输出；M1 明确为 NoOp 透传 |
| `evaluation_sample` | 逐样本位置误差、失败状态等后端评价 |
| `acoustic_range` | 已形成的距离测量及时间、锚点、有效性 |
| `communication_observation` | 目标状态或有测量来源的位置消息 |
| `measurement_received` | 已校验并接收的外部测量事实；进入缓冲不代表已经融合 |
| `measurement_unused` | 运行停止或结束时尚未交付算法的测量及未使用原因 |

准确的模型字段由 `backend/app/contracts/models.py` 与 API 的 `/openapi.json` 定义，接口文档给出各模型示例。未估计的位置和协方差用 `null`，不输出 NaN/Infinity，不以真值替代失败估计。

`GET /api/runs/{run_id}/events?after_seq=N`、`/replay?after_seq=N` 返回 N 之后的原事件数组。`WS /ws/runs/{run_id}?after_seq=N` 补发已落盘事件后继续发送新事件，运行结束后关闭。前端按 `(run_id,event_seq)` 去重，切换运行时重置游标与显示状态。

运行目录中的 JSONL 每行是一条完整事件。CSV 从已记录的评价样本导出，保留失败样本。重复性检查比较相同配置/控制条件下科学事件的类型、仿真时刻与载荷；运行 UUID、墙钟及性能耗时不属于这一相等性要求。

外部测量在接收时即记录 `measurement_received`，在其观测时刻到达后再形成对应观测事件并交给算法。无法在剩余采样时刻处理的输入明确拒绝，停止后仍在缓冲的已接收输入记录 `measurement_unused`，避免“接收成功但回放中消失”。文件导出返回后端读取的内容快照，避免下载过程中被后续重写截断。


## 0.2 波面与控制同步补充

`water_surface` 的载荷为 `WaterSurfaceSnapshot`。每一行沿 x 从小到大，行号沿 y 从小到大；高度 m、法向量无量纲，使用 LOCAL_TANK_RH。图形网格来自与折射相同的后端波面；图形三角网格和前端显示放大不参与光学求解。

暂停会等待正在计算的一步完整记录，再输出暂停确认。前端追齐该响应的事件序号后结束忙碌状态；停止则等待最终事件/元数据落盘再确认，回放只读取原事件。

未来时刻的 JSON 测量接入是有限时间窗内的仿真预排计划：接收记录表示进入队列，不表示提前取得物理测量。算法可见的 received_sim_time_s 不早于 measurement_time_s；到达时刻之前不得参与融合批次。未知设备时钟的估计仍不在此功能范围。
