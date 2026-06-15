# builtin-transition-3class

Built-in PAPI evaluation set (3-class). Seeded into the
datasets table on backend startup and used as the default evaluation set for
transition-role models.

- **Source flight:** DJI_202604291357_034_600day2up (daytime, held out of the transition train AND test splits)
- **Frames:** 24 (downscaled to 1280px longest edge, JPEG q85)
- **Split:** all frames are the `test` split (held-out evaluation only).
- **Provenance:** flight-separated from training data, so metrics are leak-free.

## Class coverage

| id | class | boxes | frames |
| -- | ----- | ----- | ------ |
| 0 | papi_light_red | 53 | 22 |
| 1 | papi_light_white | 34 | 16 |
| 2 | papi_light_transition | 9 | 9 |

Regenerate with `python workflows/scripts/build_eval_seed.py`.
