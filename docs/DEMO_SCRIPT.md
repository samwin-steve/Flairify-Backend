# Three-minute Flairify demo

Use a signed-in demonstration account and a photo you are authorized to process. Pre-stage one completed preview because live provider timing varies. Inventory prices, stock and stores remain clearly labeled samples.

**0:00–0:25 — The problem**
“Shopping usually starts with a product. Flairify starts with what you already own. Share your wardrobe once. Find pieces that work with your life—and see the look on you.” Show the light pink home page and explain the distinction between a signed-in account and the credential-free sample demo.

**0:25–1:05 — Upload once**
Sign in, enter sizes and choose photo-processing consent. Upload a clear full-body photo. Show that the photo is saved privately and automatically queues Google Gemini garment detection. Review the detected garment crops, correct anything uncertain and confirm ownership. Sizes, department and store are saved once. Photos are optional for catalogue shopping; turn on “Pair with my wardrobe” to use confirmed garments.

**1:05–1:45 — A real-life request**
Choose “Help me pack for Mumbai”: three working days, walking, ₹5,000. Show owned versus new pieces, the combined new-piece total, available sample sizes and supplied store/aisle information. Explain that each recommendation checks a complete outfit. Save a look. Open Inventory to browse the same catalogue, filter available clothing and select a photographed shirt or jacket.

**1:45–2:30 — A possibility, on you**
On a stylist look, tick the garments to preview (initially none are selected) and click “See it on me.” Generation starts directly using the uploaded reference. Inventory’s “Try this on” also starts directly. Show the background checkbox in Profile: unchecked requests white, checked preserves the source setting. Open the pre-staged result while a new job runs: show the source beside the actual Google-generated image. Explain that face likeness and garment preservation require review and that this is not an exact fit prediction. Demonstrate download and refresh persistence. Videos are not enabled in this deployment; do not present the image as motion or AR.

**2:30–2:45 — Experimental AR**
Open the 3D / AR lab. Rotate the explicitly labeled CC0 sample mannequin. Personal reconstruction and garment fitting remain separate experimental tracks; the sample is not the customer. Unsupported devices retain normal 3D viewing.

**2:45–3:00 — Google Cloud and value**
“Cloud Run serves the responsive app, API and private worker. Firestore keeps customer state; private Storage holds photos; Cloud Tasks manages jobs. Google Gemini on Vertex AI detects garments and creates 2D previews. The goal is useful purchases and more wear from clothes you already love.”

For a fully deterministic offline presentation, choose **Explore sample demo**, use the sample wardrobe and explain that anonymous sessions do not run paid generation. The sign-in prompt is an honest capability boundary, not a generated result.
