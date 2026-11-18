# todo

A small task list kept in a JSON file. Run it as `python todo.py [--file PATH] [--today YYYY-MM-DD] COMMAND ...`.

- `--file PATH`: the task file (default `todo.json` in the current directory). A missing file is an empty list.
- `--today YYYY-MM-DD`: the date used as "today" (default: the real date). Only `stats` needs it.

## Commands

| Command | Output (stdout) |
|---|---|
| `add TITLE [--priority high\|medium\|low] [--due YYYY-MM-DD]` | `Added 3: TITLE` |
| `list [--all] [--sort id\|priority\|due]` | one line per task, see below |
| `done ID` | `Done 3` |
| `delete ID` | `Deleted 3` |
| `edit ID [--title T] [--priority P] [--due YYYY-MM-DD\|none]` | `Edited 3` |
| `stats` | `open: 2, done: 1, overdue: 1` |

- Ids start at 1 and grow by one per added task. An id is never reused, also not after `delete`.
- The default priority is `medium`. `edit --due none` removes the due date; options not given keep their value.
- `list` shows open tasks only; `--all` also shows done ones. An empty list prints nothing.
- A task line is `[ ] 3 (high) Buy milk`, with ` due:2026-12-01` appended when it has a due date, and `[x]`
  instead of `[ ]` when it is done.
- `--sort id` (default): ascending id. `--sort priority`: high, then medium, then low; ties by id.
  `--sort due`: earliest due date first, tasks without a due date last; ties by id.
- `stats` counts open tasks, done tasks, and overdue tasks: open tasks whose due date is before today.

## Errors

- Unknown id (`done`, `delete`, `edit`): print `Error: no task 7` to stderr, exit code 1, file unchanged.
- A date that is not a real `YYYY-MM-DD` date: print `Error: invalid date 2026-02-30` to stderr, exit code 2,
  file unchanged.
- Success is exit code 0.

## File format

```json
{"next_id": 3, "tasks": [{"id": 1, "title": "Buy milk", "priority": "medium", "due": null, "done": false}]}
```
