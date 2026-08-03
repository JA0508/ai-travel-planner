# Plan Comparison UI Spec

## User flow

The confirmation screen leads to a route-first comparison screen only after the
intent is structurally complete. It has one question: which understandable
trade-off should become the saved trip?

Each candidate shows a plain-language strategy name, daily route timeline,
fixed-arrangement protection, travel/load/buffer comparison, and a short reason
for its trade-off. A candidate can be selected without saving it. The single
primary action is `确认并保存这条路线`.

## Progressive disclosure

Source evidence is available behind “查看依据”. It names the source phrase and
whether it came from the original description or a user confirmation. It never
shows ids, JSON, hashes, graph internals, or confidence decimals in the default
experience. Conflict states name the conflicting arrangement and show the
specific text that caused it, with a route back to edit the intent.

## Responsive rules

Desktop uses two or three comparison columns alongside a compact selected-route
detail. Mobile stacks candidates in the stable returned order and keeps the
selected candidate and primary action visible without horizontal scrolling.
Both use the same candidate response and selection state.

## Boundaries

The UI must not claim a candidate is saved before selection succeeds. It must
not render missing travel data as a confirmed duration. Retryable candidate
expiry and network failures retain the editable confirmation data.
