# Test Videos

Small MP4 fixtures for local frontend/backend smoke tests.

These clips were generated from the archived canonical sequence dataset:

```text
..\PAPI-artifacts\2026-05-26-cleanup\data\datasets\papi_lamp_sequences\
```

They are short, downscaled clips intended for upload testing only. Do not use
them for training or evaluation metrics.

## Fixtures

| File | Source sequence | Frames | Size |
|---|---|---:|---|
| `daytime_DJI_202604281946_011_700_smoke.mp4` | `daytime/DJI_202604281946_011_700` | 18 | 960x720 |
| `daytime_DJI_202604291738_041_300mday2up_smoke.mp4` | `daytime/DJI_202604291738_041_300mday2up` | 18 | 960x720 |
| `nighttime_DJI_202604290007_019_300mRwy06night_smoke.mp4` | `nighttime/DJI_202604290007_019_300mRwy06night` | 18 | 960x720 |

## Smoke Command

```powershell
curl.exe -X POST `
  -F "file=@test_videos\nighttime_DJI_202604290007_019_300mRwy06night_smoke.mp4" `
  -F "runway_id=papi_06" `
  http://127.0.0.1:8000/api/analyze
```
