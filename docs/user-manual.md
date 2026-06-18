# PAPI Lights Detection and Classification — User Manual

This guide shows you how to use the PAPI app. It is written for the
people who run it — drone operators, review engineers, and anyone
checking PAPI lights. You do not need to know how the code works.

To install the app first, see the
[installation manual](installation-manual.md).

## 1. What the app does

You give it a drone photo or video of a runway's four PAPI lights.
It tells you:

- The colour of each of the four lamps: **white**, **red**, or
  **changing** (in between).
- The overall glidepath verdict — what the lamp pattern means for the
  approach:

  | Lamps | Meaning |
  | --- | --- |
  | 4 white | Far too high |
  | 3 white, 1 red | A little too high |
  | 2 white, 2 red | On the correct path |
  | 1 white, 3 red | A little too low |
  | 4 red | Far too low |
  | Transition | A lamp is mid-change between red and white |

- The drone's viewing angle to the lights — when the photo or video
  carries GPS and height information.
- A copy of your image or video with the lights boxed and labelled.

The app was trained on footage from **Bodensee-Airport
Friedrichshafen (EDNY)**. It can be set up for other airports later.

## 2. Getting started

Open the app in your browser:

```
http://localhost:5173/
```

You land on the **Introduction** page. Across the top is the menu you
use to move around:

- **Introduction** — the welcome page.
- **Live Demo** — upload footage and get a result. This is the main page.
- **Runways** — manage the runways the app knows.
- **Insights** — charts that explain the latest result.
- **History** — past results.

Two more items, **Models** and **Datasets**, appear only after you
unlock admin mode (see section 9).

### The Introduction page

The Introduction page is a welcome screen — nothing here changes your
data. It has:

- A short summary of the four things the app reports.
- An interactive **glide path simulator**. Drag the **Approach angle**
  slider (2.0° to 4.0°) and watch the four lamps change colour and the
  verdict update — from "Far too low", through "Correct glidepath", to
  "Far too high". Click **Sweep** to play the angle up and down on its
  own. It is a quick way to learn how PAPI lights work.
- An **airport snapshot** for Friedrichshafen, with a small map.

Click **Try it out** (or **Live Demo** in the menu) to start.

## 3. Live Demo — analysing footage

This is where you do the real work. You can try it with the built-in
examples or upload your own footage.

### 3.1 Try it with the built-in samples

If you have no footage of your own, use the ready-made examples. On the
empty page, under the upload buttons, you will see three sample cards:

- **Sample image** — one frame on the correct path (two white, two red).
- **Sample image set** — ten frames that climb through every PAPI state.
- **Sample video** — a two-minute clip of a full climb, including each
  lamp changing from red to white. It takes about half a minute.

Click any card and the analysis starts on its own. The runway and drone
position are filled in for you.

### 3.2 Analyse your own footage

Before you upload, set two things at the top of the page:

1. **Analysis runway** — pick the runway the drone was facing. The
   default is **PAPI 24**. Choose **PAPI 06** for the other approach.
2. **Inference model** (optional) — which detector to use. The default
   (**Small detector**) is right for normal use. Other models appear
   here if they are installed.

Then upload, in one of three ways:

- **One image** — click **Upload media** and choose a photo (JPG, PNG,
  BMP, or WEBP). The analysis starts as soon as the file loads — there
  is no separate "run" button.
- **A video** — same button; choose a video (MP4, MOV, AVI, or MKV).
  The app reads the frames and gives one combined result plus an
  annotated video.
- **A folder of images** — click **Upload folder**, then choose how to
  treat them:
  - **Angle sweep** (the default) — each image is analysed on its own,
    with its own angle. Use this to compare angles across a descent. It
    is what feeds the charts on the Insights page.
  - **Video sequence** — the images are treated as one video, in
    filename order. The app tracks the lamps across frames and finds the
    red↔white changes over time. You get one combined result. Name the
    files in order (for example `frame_000.jpg`, `frame_001.jpg`, …).

If you change the runway, model, or folder mode after a run, click
**Re-run analysis** to apply it.

### 3.3 If the app asks for the drone position

If your file has no GPS or height information, a **"No drone metadata
found"** notice appears. To get the viewing angle, fill in
**Latitude**, **Longitude**, and **Altitude (m)** — all three, or none
— and click **Apply metadata**. You can also upload a telemetry file.
If you skip this, you still get the colour result, just without an angle.

### 3.4 File limits

- Up to **100 MB** per upload.
- Up to **600 frames** and **150 seconds** per video.

If a video is damaged and only part of it can be read, you get a
warning saying how many frames were used, and the result covers only
those frames. It is marked **Partial** in History.

## 4. Reading the result

After a run, the middle of the page shows your image or video with the
lamps boxed. The right side shows the verdict.

- **Top:** a coloured dot and a large label give the **overall
  verdict** (for example "Correct glidepath" or "Too low"). The line
  under it shows the lamp pattern behind the verdict.
- **Lamp cards:** one card per lamp, left to right. Each shows the lamp
  number (1–4), its colour (White, Red, Transition, or Occluded if it
  cannot be seen), and how sure the app is (0–100%). A weak detection
  (under 50%) is flagged, so a shaky reading is not shown as certain.
- **Two small cards at the bottom:**
  - **Detection confidence** — the average confidence over the four
    lamps.
  - **Processing time** — how long the analysis took, in milliseconds.

These numbers are real measurements, not examples. The result panel
stays empty until you run something.

## 5. Insights — charts that explain a result

Click **Insights** in the menu. It explains your most recent Live Demo
run, or a run you opened from History. Every chart uses real results —
nothing is faked.

When the data is there, you will see:

- **Transition angle per light** — where each lamp changed between red
  and white.
- **Redness vs. angle** — one graph per lamp, plotting colour against
  viewing angle. This is the main evidence chart for the client.
- **Lamp state over the sweep** and **Elevation angle over frame** —
  the descent, frame by frame.
- **Session distributions** — the mix of lamp states and confidence for
  the run.
- **Model & dataset** — the facts about the model and data behind the
  result.

Top right:

- **Download charts (PDF)** — save the charts as a PDF for a report.
- **Download transitions (CSV)** — save the raw red↔white change events
  as a spreadsheet (when there are any).

If you have not run anything yet, the page points you back to Live Demo.

## 6. History — past results

Click **History** to see earlier runs, newest first. Each row shows the
verdict, runway, confidence, and the annotated file. History needs the
app's backend running.

Narrow the list with the **filters**: runway, state, model, media type
(images or videos), a date ("on or after"), and a minimum confidence.
The summary cards above the table always match the rows you have
filtered to, and show a small **"filtered"** chip when a filter is on.

- **Export CSV** — download the filtered rows as a spreadsheet.
- **Click a row** — open the full detail, with each lamp's state and the
  annotated file.
- **Insights** (on a row) — open that run in the Insights page without
  analysing it again.

## 7. Runways

Click **Runways** to see the runways the app can score an approach
against. Each runway holds the positions of its four PAPI lamps, which
the app uses to work out the viewing angle.

- Built-in runways (like EDNY) come with the app and cannot be changed.
- To add your own runway, enter its four lamp coordinates. It then
  appears in the runway dropdown on the Live Demo page.
- You can delete runways you added (built-in ones are protected).

You only need this page for a runway the app does not already know. For
the sample footage, a runway is chosen for you.

## 8. Language and theme

In the top-right corner:

- **Language** — click the language button (EN) to switch between
  **English, Deutsch, Nederlands, Français**. The text changes straight
  away, and your choice is remembered.
- **Light / dark mode** — the sun/moon button switches the look. Handy
  for dark rooms during a demo. Also remembered.

## 9. Advanced: managing models and data (admin)

These features are for technical users who maintain the app. They are
hidden until you unlock admin mode.

### Unlocking admin mode

Click the **shield icon** in the top-right corner, type the **API key**,
and click **Unlock**. On a normal local setup you can leave the key
blank. Two new menu items appear: **Models** and **Datasets**. Click the
shield again to lock it.

### The Models page

Click **Models** to manage the detectors. Each model shows its accuracy
scores (mAP, precision, recall, F1) and details. Not sure what the
scores mean? Click **"What do these scores mean?"** for plain
definitions. You can:

- **Set default** — make a model the one used when a request does not
  pick one (also the Live Demo's starting choice).
- **Evaluate** — test a model on a dataset and split; the result fills
  in its scores.
- **Compare** — tick two or more models to see them side by side.
- **Enable / Disable** and **Delete** — manage which models show
  (built-in ones are protected).
- **Upload model** — add your own model file (`.pt` or `.onnx`), give it
  a name and a role (detector or transition). Only upload model files
  you trust.

Long jobs such as an evaluation show in a **jobs panel** with a progress
bar; you can cancel a running job or clear finished ones.

### The Datasets page

Click **Datasets** to manage training data. Each dataset shows its type,
its classes, and its train / validation / test counts. You can:

- **Upload dataset** — add a labelled YOLO dataset as a `.zip`.
- **Assisted labeling** — upload plain images and pick a model to
  pre-label them. Then **Review labels**: fix or delete the predicted
  boxes, skip bad images, and click **Commit labels**.
- **Train** — on a ready dataset, set the options (epochs, image size,
  batch, transition oversample) and click **Download bundle**. You run
  the training on your own GPU, then bring the new model back with
  **Upload model**.

As on the Models page, running jobs appear in the jobs panel.

## 10. Troubleshooting

| Problem | Why | What to do |
| --- | --- | --- |
| "Angle unavailable" on a result | The file had no GPS / height info | Type the drone position in the metadata fields |
| Asked to fill all three position fields | You filled some but not all of latitude, longitude, altitude | Fill all three, or clear all three |
| "Only N of M frames could be read" | The video is damaged or only partly uploaded | Re-export and upload again; the result covers the readable frames |
| Upload rejected as too large | The file is over 100 MB | Trim or compress it |
| "Too many requests" | You sent many analyses very quickly | Wait a moment and try again |
| Charts say "unavailable" | A chart failed to load (offline, ad-blocker) | Refresh the page |
| Folder upload shows only one image | The browser could not read the folder | Try Firefox or Edge |

To see exactly what the backend received, open the built-in API docs at
`http://localhost:8000/docs`.

## 11. Good to know

- The app is tuned for **Friedrichshafen (EDNY)**. Other airports need
  retraining and a new runway setup.
- On a normal laptop (no GPU) a video is slow — roughly **0.4 frames per
  second**. A GPU is much faster.
- The set angles shown for transitions are FAA defaults, used as
  reference lines until the real commissioned angles are added.
- Some daytime footage with strong lens flare can make a red lamp look
  white. These cases are known.

## 12. Help and feedback

- **Software bugs:** open an issue on the project's
  [GitHub page](https://github.com/MaximRoomsHowest/PAPI-Detection-and-Classification/issues).
- **Model or data questions:** the team's knowledge base is the working
  reference.
- **Client questions:** go through Intersoft Electronics Services BV
  (via the team supervisor).
