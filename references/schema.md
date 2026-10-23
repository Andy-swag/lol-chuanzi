# 数据约定

`data/memes.json` 是记录数组。`kind` 为 `meme`（典故）、`slang`（通行黑话）、`mechanic`（游戏/赛制术语）。

| 字段 | 含义 |
|---|---|
| id / term / aliases | 稳定 ID、主词面、同义写法 |
| year | 所述场景的年份；null 表示不指定首发年 |
| event_date | 可选，明确事件日期 YYYY-MM-DD；不是网页采集日期 |
| subjects | 关联 `entities.json` ID；没有特定人物可为空 |
| tags | 行为、位置或场景检索词 |
| meaning | 独立编写的简要释义 |
| context | 可确认的背景与时间范围，不认领首创权 |
| use_when / avoid | 使用触发与误用提示 |
| heat | 0—3，表达尖锐度参考，不是允许攻击人的等级 |
| evidence | verified / community / glossary / provisional |
| sources | `sources.json` 的来源 ID，可多条；通行词可为空 |
| checked_at | 最近整理日，不意味着此日所有外链仍可访问 |

`entities.json` 保存人物与队伍的名称、别名、类型及语境说明，不保存动态阵容。别名仅用于理解，不代表建议在每次输出中使用。

`sources.json` 保存 URL、标题、来源类型、`access`（full_text / excerpt / video_metadata）以及 `supports`。它是核验入口，不是网页内容授权。`verified` 指可支持的事实范围，不担保网页绝对正确。

`--as-of`：带 `event_date` 的记录按日过滤；只有 `year` 的记录以该年末作为保守可用日。无年份的通行术语不会被过滤，**因此这个选项不是某个年代完整词汇的重建**。确切日期未定的当年梗可能被保守排除。

`--year` 精确筛选记录的场景年份，不代表它仅在该年流行。`--heat` 筛选不超过该火力的条目。`--include-provisional` 只便于考据，不能将线索升级成事实。
