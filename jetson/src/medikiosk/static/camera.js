// Photograph a document with the connecting device's own camera and OCR it on the Jetson.
// Independent of app.js's voice session - a phone or tablet screen can run one, both, or neither.

const cam = {
  start: document.querySelector("#camStart"),
  shot: document.querySelector("#camShot"),
  stop: document.querySelector("#camStop"),
  status: document.querySelector("#camStatus"),
  video: document.querySelector("#camVideo"),
  result: document.querySelector("#camResult"),
  timing: document.querySelector("#camTiming"),
};

let camStream;

async function startCamera() {
  try {
    // The rear camera on a phone/tablet has real autofocus, unlike the kiosk's wired sensor.
    camStream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: { ideal: "environment" }, width: { ideal: 1920 }, height: { ideal: 1440 } },
      audio: false,
    });
    cam.video.srcObject = camStream;
    await cam.video.play();
    cam.start.disabled = true;
    cam.shot.disabled = false;
    cam.stop.disabled = false;
    cam.status.textContent = "Camera live";
  } catch (error) {
    cam.status.textContent = `Camera unavailable: ${error.message}`;
  }
}

function stopCamera() {
  camStream?.getTracks().forEach((track) => track.stop());
  camStream = undefined;
  cam.video.srcObject = null;
  cam.start.disabled = false;
  cam.shot.disabled = true;
  cam.stop.disabled = true;
  cam.status.textContent = "Camera off";
}

async function captureAndRead() {
  if (!camStream) return;
  cam.shot.disabled = true;
  cam.status.textContent = "Reading…";
  cam.timing.textContent = "";
  const t0 = performance.now();
  try {
    const canvas = document.createElement("canvas");
    canvas.width = cam.video.videoWidth;
    canvas.height = cam.video.videoHeight;
    canvas.getContext("2d").drawImage(cam.video, 0, 0);
    const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.92));

    const form = new FormData();
    form.append("image", blob, "capture.jpg");
    const response = await fetch("/api/ocr", { method: "POST", body: form });
    if (!response.ok) throw new Error(`server returned ${response.status}`);
    const data = await response.json();

    const roundTrip = ((performance.now() - t0) / 1000).toFixed(1);
    cam.timing.textContent = `${data.lines.length} line(s) · read ${data.seconds}s · round trip ${roundTrip}s`;
    cam.result.textContent = data.lines.length
      ? data.lines.join("\n")
      : "No text recognized. Hold the document flat, filling the frame, well lit.";
  } catch (error) {
    cam.result.textContent = `Read failed: ${error.message}`;
  } finally {
    cam.status.textContent = "Camera live";
    cam.shot.disabled = false;
  }
}

cam.start.addEventListener("click", startCamera);
cam.stop.addEventListener("click", stopCamera);
cam.shot.addEventListener("click", captureAndRead);
