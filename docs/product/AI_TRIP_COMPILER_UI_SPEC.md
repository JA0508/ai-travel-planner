# AI Trip Compiler V1 UI Specification

## Page states and primary actions

| State | User task | Primary action |
| --- | --- | --- |
| Input | Paste fragmented travel thoughts | `整理我的旅行想法` |
| Confirmation | Review and correct typed intent | `生成我的行程骨架` |
| Route | Follow a saved daily skeleton | `让这一天轻松一些` when the server marks a day rushed |
| Repair review | Compare a server proposal | `应用这次调整` |
| Conflict / network error | Correct or retry | `修改旅行信息` / `返回继续修改` |

## Information hierarchy

1. The current user task and one primary CTA.
2. Destination, duration, pace, and fixed arrangements.
3. Day timeline: activity, time, route leg, and daily load.
4. Explanations, source text, and unresolved questions through progressive
   disclosure.

No default screen may expose IDs, revision numbers, traces, digests, raw JSON,
or API diagnostics.

## Visual system

- **Temperature:** editorial travel, calm and trustworthy.
- **Palette:** warm white background, deep ink text, muted slate metadata,
  restrained green emphasis; red only for actionable conflicts.
- **Typography:** serif display/page title; system sans-serif for route metadata
  and controls. Time is clear but secondary to the activity name.
- **Spacing:** 4, 8, 12, 16, 24, 32, 48, and 64 pixel increments.
- **Borders:** thin neutral rules; 5-10px corners for controls and 16-20px only
  for the main route surfaces. Shadows are subtle and limited to primary
  working surfaces.

## Timeline rules

Activities use the route timeline. Travel legs are visually separate and always
name their origin and destination. Labels have semantic meaning:

- `必去`: confirmed must-visit.
- `可调整`: confirmed optional place.
- `已预约 · 不可随意移动`: fixed event.
- `系统补充`: server-added meal, anchor, or fill item.

An explanation is displayed only from server `placement_reason`; absent evidence
renders `暂时没有可验证的安排说明` rather than a client fallback.

## Responsive behavior

- Desktop uses a 1120-1160px constrained canvas; the input page may split copy
  and composer, while route content remains a single dominant column.
- At 760px and below, all content becomes one column. The repair comparison
  stacks vertically, controls wrap, and the sticky CTA never obscures content.
- Details sections remain collapsed by default. Focus states, keyboard actions,
  alert semantics, and `prefers-reduced-motion` are required.

## Disallowed patterns

No AI gradients, glass panels, dashboard badge walls, decorative maps, repeated
activity cards, or technical information walls. A route may be dense, but must
remain scannable as a sequence of time, place, movement, and reason.
