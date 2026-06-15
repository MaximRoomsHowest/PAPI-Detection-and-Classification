# builtin-detector-redwhite

Built-in PAPI evaluation set (2-class). Seeded into the
datasets table on backend startup and used as the default evaluation set for
detector-role models.

- **Source flight:** DJI_202604281946_014_1000 (redwhite_test_view, daytime red/white test view)
- **Frames:** 18 (downscaled to 1280px longest edge, JPEG q85)
- **Split:** all frames are the `test` split (held-out evaluation only).
- **Provenance:** flight-separated from training data, so metrics are leak-free.

## Class coverage

| id | class | boxes | frames |
| -- | ----- | ----- | ------ |
| 0 | papi_light_red | 33 | 16 |
| 1 | papi_light_white | 39 | 16 |

Regenerate with `python workflows/scripts/build_eval_seed.py`.
