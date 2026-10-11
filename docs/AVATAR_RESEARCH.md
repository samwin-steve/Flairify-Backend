# Experimental 3D / AR findings

Research checked 11 October 2026. No GPU was launched and no reconstruction quality measurements were collected.

| Option | Code / model weights | Capture & hardware | Output & feasibility | Decision |
| --- | --- | --- | --- | --- |
| TripoSR | Repository explicitly says MIT covers code, pretrained models and demo; commercially permissive, subject to dependency and input rights | One image; project states about 6 GB VRAM at defaults | Mesh with vertex colours or baked texture. General object reconstruction. Recognizable face, accurate body, rigging, animation and physically accurate garment fitting are not established | Eligible for a separately budgeted experiment, unsuitable as a claimed production avatar |
| ECON | Repository license restricts non-commercial scientific research; dependencies such as SMPL-X have their own model licenses | Human image plus associated reconstruction dependencies. End-to-end target GPU/memory not benchmarked here | Clothed-human geometry; does not establish an editable, rigged, commercially licensed wardrobe try-on pipeline | Not integrated for retail deployment |
| MediaPipe Face/Pose Landmarker | Google documentation and package licensing must be verified together with chosen task assets before shipping | On-device camera with separate permission; browser/device-dependent performance | Landmarks and optional blendshapes/pose signals. Does not reconstruct a photorealistic avatar or garment mesh | Optional future tracking input, not an avatar replacement |
| model-viewer | Apache-2.0 web component; each displayed asset needs its own license | GLB/glTF. AR requires compatible device/browser and HTTPS | Camera controls plus device-specific AR placement. No avatar reconstruction or garment fitting | Integrated using an original CC0 sample studio form |

Primary sources: [TripoSR repository](https://github.com/VAST-AI-Research/TripoSR), [ECON license](https://github.com/YuliangXiu/ECON/blob/master/LICENSE), [MediaPipe vision tasks](https://ai.google.dev/edge/mediapipe/solutions/vision/face_landmarker/web_js), [model-viewer](https://modelviewer.dev/).

Separate development stages:

1. **Reconstruction:** validate capture requirements, commercially usable code and weights, face likeness, body fidelity and texture quality on consenting adults.
2. **Rigging / expression:** skeleton, skinning and expression correspondence are separate work. Pose landmarks and facial blendshapes alone are insufficient.
3. **Garments:** obtain licensed, dimensioned 3D garment assets and validate fitting / collision. A retail photograph does not supply hidden geometry.
4. **Rendering / AR:** export valid GLB, test scale, materials and mobile memory; use model-viewer and a normal 3D fallback.

`frontend/public/models/flairify-form.glb` is an original procedural sample under CC0. It is deliberately a faceless mannequin, labeled as a sample and never described as the customer. It has no animation rig. AR device placement has not been tested on physical iOS/Android hardware. No personalized avatar endpoint reports success.
